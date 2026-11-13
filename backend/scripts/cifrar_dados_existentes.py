"""
Migra os dados JA EXISTENTES para o modelo de seguranca (Confidencialidade + Integridade). Uso, a partir de backend/:

    python scripts/cifrar_dados_existentes.py --dry-run          # so conta o que seria feito (nao grava nada)
    python scripts/cifrar_dados_existentes.py                    # campos + payload do sync + assinaturas + hashes
    python scripts/cifrar_dados_existentes.py --campos           # so cifra os campos sensiveis e preenche tecnico.cnpj_idx
    python scripts/cifrar_dados_existentes.py --payload-sync     # so cifra documento_cliente/nome_cliente em sync_evento.payload
    python scripts/cifrar_dados_existentes.py --assinaturas      # converte assinaturas em claro para .enc (AES-256-GCM)
    python scripts/cifrar_dados_existentes.py --hashes           # preenche sha256 das fotos/comprovantes que existem em disco
    python scripts/cifrar_dados_existentes.py --verificar        # SOMENTE LEITURA: lista pendencias; codigo de saida != 0 se houver
    python scripts/cifrar_dados_existentes.py --decifrar         # REVERTE campos e payload para texto puro (pre-requisito dos rollbacks 0011/0014)
    ... --apagar-originais                                       # (com --assinaturas) apaga a assinatura em claro apos conferir o .enc

--campos e --payload-sync sao INDEPENDENTES (H1 = payload do sync, sem DDL; H2 = campos de cliente/visita, exige a migracao 0014).
Sem seletor, --verificar e --decifrar atuam em campos + payload; com --campos ou --payload-sync, so no escolhido.

PRE-REQUISITOS: backup (scripts/backup_banco.py) e migracoes 0010 e 0011 aplicadas (para cliente.contato_principal_* e
visita.nome_cliente_assinatura tambem a 0014: sem ela o valor cifrado nao cabe em VARCHAR(100)/(20)). Usa o DATABASE_URL do .env
(o MESMO banco da API) e as chaves do .env (DATA_ENCRYPTION_KEY, INDEX_KEY). E IDEMPOTENTE: valores que ja comecam com "enc1:" e
arquivos que ja sao .enc sao ignorados; pode ser repetido. Cada tabela e gravada em UMA transacao (tudo ou nada).
Nunca imprime valores sensiveis, apenas contagens e IDs.

Depois de rodar sem erros: aplique 0012_cnpj_idx_obrigatorio.sql e defina ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false no .env.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text, update  # noqa: E402

from app.core import crypto  # noqa: E402
from app.models.sync_evento import SyncEvento  # noqa: E402
from app.services import file_service  # noqa: E402
from app.services.sync_service import CHAVES_PESSOAIS_PAYLOAD, contexto_payload  # noqa: E402

# tabela -> (coluna da chave primaria, [colunas cifradas])
CAMPOS_CIFRADOS = {
    "tecnico": ("id_tecnico", ["cnpj", "cpf", "telefone", "banco", "agencia", "conta", "pix"]),
    "visita": ("id_visita", ["documento_cliente", "nome_cliente_assinatura"]),
    "cliente": ("id_cliente", ["contato_principal_nome", "contato_principal_telefone"]),
}


def _contexto(tabela: str, coluna: str) -> str:
    return f"{tabela}.{coluna}"


def _indice_cnpj(cnpj_claro: str) -> str:
    return crypto.indice_cego(re.sub(r"\D", "", cnpj_claro or ""), "tecnico.cnpj")


# ---------------------------------------------------------------------------------------------------------------------
def cifrar_campos(engine, dry_run: bool = False) -> Dict[str, int]:
    """Cifra CAMPOS_CIFRADOS e preenche tecnico.cnpj_idx. Retorna {tabela.coluna: n_cifrados}. Uma transacao por tabela."""
    resumo: Dict[str, int] = {}
    for tabela, (pk, colunas) in CAMPOS_CIFRADOS.items():
        with engine.begin() as conn:
            extra = ", cnpj_idx" if tabela == "tecnico" else ""
            linhas = conn.execute(text(f"SELECT {pk}, {', '.join(colunas)}{extra} FROM {tabela} ORDER BY {pk}")).fetchall()
            for linha in linhas:
                id_ = linha[0]
                novos: Dict[str, Optional[str]] = {}
                for i, col in enumerate(colunas, start=1):
                    valor = linha[i]
                    if valor is None or crypto.esta_cifrado(valor):
                        continue
                    novos[col] = crypto.cifrar(valor, _contexto(tabela, col))
                    resumo[f"{tabela}.{col}"] = resumo.get(f"{tabela}.{col}", 0) + 1
                if tabela == "tecnico" and linha[-1] is None:  # cnpj_idx ainda vazio (cnpj em claro ou ja cifrado)
                    cnpj = linha[1]
                    claro = crypto.decifrar(cnpj, "tecnico.cnpj") if crypto.esta_cifrado(cnpj) else cnpj
                    novos["cnpj_idx"] = _indice_cnpj(claro)
                    resumo["tecnico.cnpj_idx"] = resumo.get("tecnico.cnpj_idx", 0) + 1
                if novos and not dry_run:
                    sets = ", ".join(f"{c} = :{c}" for c in novos)
                    conn.execute(text(f"UPDATE {tabela} SET {sets} WHERE {pk} = :_id"), {**novos, "_id": id_})
    return resumo


def decifrar_campos(engine, dry_run: bool = False) -> Dict[str, int]:
    """Reverte para texto puro (pre-requisito dos rollbacks 0011/0014). Mantem cnpj_idx. Uma transacao por tabela."""
    resumo: Dict[str, int] = {}
    for tabela, (pk, colunas) in CAMPOS_CIFRADOS.items():
        with engine.begin() as conn:
            linhas = conn.execute(text(f"SELECT {pk}, {', '.join(colunas)} FROM {tabela} ORDER BY {pk}")).fetchall()
            for linha in linhas:
                novos = {}
                for i, col in enumerate(colunas, start=1):
                    if crypto.esta_cifrado(linha[i]):
                        novos[col] = crypto.decifrar(linha[i], _contexto(tabela, col))
                        resumo[f"{tabela}.{col}"] = resumo.get(f"{tabela}.{col}", 0) + 1
                if novos and not dry_run:
                    sets = ", ".join(f"{c} = :{c}" for c in novos)
                    conn.execute(text(f"UPDATE {tabela} SET {sets} WHERE {pk} = :_id"), {**novos, "_id": linha[0]})
    return resumo


def colunas_nao_text(engine) -> List[str]:
    """
    PostgreSQL: colunas de CAMPOS_CIFRADOS que ainda NAO sao `text` (ex.: contato_principal_* e nome_cliente_assinatura antes
    da 0014). Cifrar nelas estouraria VARCHAR(100)/(20). SQLite: nao checa (tipos sao flexiveis).
    """
    if engine.dialect.name != "postgresql":
        return []
    ruins: List[str] = []
    with engine.connect() as conn:
        for tabela, (_pk, colunas) in CAMPOS_CIFRADOS.items():
            tipos = dict(conn.execute(
                text("SELECT column_name, data_type FROM information_schema.columns "
                     "WHERE table_schema = current_schema() AND table_name = :t"), {"t": tabela}).fetchall())
            ruins += [f"{tabela}.{c}" for c in colunas if tipos.get(c) != "text"]
    return ruins


def verificar_campos(engine) -> Dict[str, int]:
    """Quantas linhas ainda estao em claro por coluna (0 em tudo = migracao completa) + tecnicos sem cnpj_idx."""
    pendentes: Dict[str, int] = {}
    with engine.connect() as conn:
        for tabela, (_pk, colunas) in CAMPOS_CIFRADOS.items():
            for col in colunas:
                n = conn.execute(text(f"SELECT count(*) FROM {tabela} WHERE {col} IS NOT NULL "
                                      f"AND {col} NOT LIKE 'enc1:%'")).scalar()
                pendentes[f"{tabela}.{col}"] = n
        pendentes["tecnico.cnpj_idx_nulo"] = conn.execute(text("SELECT count(*) FROM tecnico WHERE cnpj_idx IS NULL")).scalar()
    return pendentes


# ---------------------------------------------------------------------------------------------------------------------
# sync_evento.payload (JSONB; PK = client_event_id UUID): cifra POR CHAVE as chaves de CHAVES_PESSOAIS_PAYLOAD, nas linhas
# aplicadas E rejeitadas (qualquer tipo de evento), com AAD POR LINHA (`sync_evento.<chave>|<client_event_id>`). Usa a
# tabela do modelo (Core) para o UUID e o JSON funcionarem igual em PostgreSQL e SQLite. Valor None fica None; valor
# nao-string e serializado em JSON e cifrado (ao decifrar volta como o TEXTO JSON: o round-trip EXATO so vale para strings).
# Idempotencia pelo prefixo "enc1:" SE o valor decifra com o contexto da linha; "enc1:" que NAO decifra (forjado, de outra
# linha ou chave errada) e ANOMALIA: no cifrar e tratado como texto em claro (cifrado por cima); no decifrar e no
# --verificar apenas e reportado por ID, sem derrubar a transacao.
# ---------------------------------------------------------------------------------------------------------------------
_SYNC = SyncEvento.__table__
LEGIVEL, CIFRADO, ANOMALO = "legivel", "cifrado", "anomalo"


def _estado_chave(valor, chave: str, id_) -> str:
    """LEGIVEL (a cifrar), CIFRADO (enc1: valido nesta linha) ou ANOMALO (enc1: que nao decifra)."""
    if not crypto.esta_cifrado(valor):
        return LEGIVEL
    try:
        crypto.decifrar(valor, contexto_payload(chave, id_))
        return CIFRADO
    except crypto.ErroDecifragem:
        return ANOMALO


def _linhas_sync(conn):
    for id_, payload in conn.execute(select(_SYNC.c.client_event_id, _SYNC.c.payload)).fetchall():
        if isinstance(payload, dict):
            yield id_, payload


def cifrar_payload_sync(engine, dry_run: bool = False, anomalias: Optional[List[str]] = None) -> Dict[str, int]:
    """
    Cifra as chaves pessoais do payload de sync_evento. Retorna {'sync_evento.payload.<chave>': n, 'eventos': n_linhas}.
    `anomalias` (lista opcional) recebe o client_event_id dos eventos com `enc1:` que nao decifrava (cifrados por cima).
    """
    resumo: Dict[str, int] = {}
    with engine.begin() as conn:  # uma transacao para a tabela
        for id_, payload in _linhas_sync(conn):
            novo = dict(payload)
            anomalo = False
            for chave in CHAVES_PESSOAIS_PAYLOAD:
                valor = payload.get(chave)
                if valor is None:
                    continue
                estado = _estado_chave(valor, chave, id_)
                if estado == CIFRADO:
                    continue
                anomalo = anomalo or estado == ANOMALO
                texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=True, default=str)
                novo[chave] = crypto.cifrar(texto.encode("utf-8", "backslashreplace").decode("utf-8"),
                                            contexto_payload(chave, id_))
                resumo[f"sync_evento.payload.{chave}"] = resumo.get(f"sync_evento.payload.{chave}", 0) + 1
            if novo == payload:
                continue
            resumo["eventos"] = resumo.get("eventos", 0) + 1
            if anomalo:
                resumo["anomalias"] = resumo.get("anomalias", 0) + 1
                if anomalias is not None:
                    anomalias.append(str(id_))
            if not dry_run:
                conn.execute(update(_SYNC).where(_SYNC.c.client_event_id == id_).values(payload=novo))
    return resumo


def decifrar_payload_sync(engine, dry_run: bool = False, anomalias: Optional[List[str]] = None) -> Dict[str, int]:
    """
    Reverte as chaves pessoais do payload para texto puro (pre-requisito do rollback). ATENCAO: round-trip EXATO so para
    valores que eram string; nao-string (int, dict...) volta como o texto JSON. `enc1:` que nao decifra NAO derruba a
    transacao: fica como esta e o ID entra em `anomalias`.
    """
    resumo: Dict[str, int] = {}
    with engine.begin() as conn:
        for id_, payload in _linhas_sync(conn):
            novo = dict(payload)
            for chave in CHAVES_PESSOAIS_PAYLOAD:
                valor = payload.get(chave)
                if not crypto.esta_cifrado(valor):
                    continue
                if _estado_chave(valor, chave, id_) == ANOMALO:
                    resumo["anomalias"] = resumo.get("anomalias", 0) + 1
                    if anomalias is not None:
                        anomalias.append(str(id_))
                    continue
                novo[chave] = crypto.decifrar(valor, contexto_payload(chave, id_))
                resumo[f"sync_evento.payload.{chave}"] = resumo.get(f"sync_evento.payload.{chave}", 0) + 1
            if novo == payload:
                continue
            resumo["eventos"] = resumo.get("eventos", 0) + 1
            if not dry_run:
                conn.execute(update(_SYNC).where(_SYNC.c.client_event_id == id_).values(payload=novo))
    return resumo


def verificar_payload_sync(engine) -> Tuple[Dict[str, int], List[str]]:
    """
    SOMENTE LEITURA. Retorna (contagens, ids): por chave, quantos eventos ainda tem valor legivel; e quantos `enc1:` NAO
    decifram (anomalia). ids = client_event_id dos eventos com pendencia ou anomalia (nunca valores). Anomalia nao trava
    o script: o `cifrar` a corrige (cifra por cima) e, no `--decifrar`, ela so e reportada.
    """
    contagens: Dict[str, int] = {f"sync_evento.payload.{c}": 0 for c in CHAVES_PESSOAIS_PAYLOAD}
    contagens["sync_evento.payload_anomalo"] = 0
    ids: List[str] = []
    with engine.connect() as conn:
        for id_, payload in _linhas_sync(conn):
            problema = False
            for chave in CHAVES_PESSOAIS_PAYLOAD:
                valor = payload.get(chave)
                if valor is None:
                    continue
                estado = _estado_chave(valor, chave, id_)
                if estado == LEGIVEL:
                    contagens[f"sync_evento.payload.{chave}"] += 1
                    problema = True
                elif estado == ANOMALO:
                    contagens["sync_evento.payload_anomalo"] += 1
                    problema = True
            if problema:
                ids.append(str(id_))
    return contagens, ids


# ---------------------------------------------------------------------------------------------------------------------
def converter_assinaturas(engine, dry_run: bool = False, apagar_originais: bool = False) -> Dict[str, List]:
    """
    Assinatura em claro (/static/assinaturas/x.png|jpg) -> .enc. Atualiza visita.assinatura_url/assinatura_sha256 e
    sync_arquivo.url/sha256 e CONFERE (decifra e compara) antes de considerar convertida. Arquivo ausente em disco
    e apenas reportado (nao inventa nada). O original so e apagado com apagar_originais=True.
    """
    resultado: Dict[str, List] = {"convertidas": [], "ausentes": [], "ja_cifradas": [], "apagadas": []}
    prefixo = file_service.ASSINATURA_URL_PREFIX + "/"
    with engine.begin() as conn:
        linhas = conn.execute(text("SELECT id_visita, assinatura_url FROM visita WHERE assinatura_url IS NOT NULL "
                                   "ORDER BY id_visita")).fetchall()
        for id_visita, url in linhas:
            if url.endswith(".enc"):
                resultado["ja_cifradas"].append(id_visita)
                continue
            nome = url.rsplit("/", 1)[-1]
            origem = file_service.ASSINATURA_DIRECTORY / nome
            if not url.startswith(prefixo) or not origem.is_file():
                resultado["ausentes"].append(id_visita)
                continue
            original = origem.read_bytes()
            if dry_run:
                resultado["convertidas"].append(id_visita)
                continue
            imagem = file_service._analisar_imagem(original)  # valida que e imagem JPEG/PNG integra
            nova_url = file_service.salvar_assinatura(imagem)
            if file_service.ler_arquivo_por_url(nova_url) != original:  # confere ANTES de apontar o banco para o .enc
                raise RuntimeError(f"Conferencia falhou para a visita {id_visita}; nada foi alterado no banco para ela.")
            conn.execute(text("UPDATE visita SET assinatura_url = :n, assinatura_sha256 = :h WHERE id_visita = :i"),
                         {"n": nova_url, "h": imagem.sha256, "i": id_visita})
            conn.execute(text("UPDATE sync_arquivo SET url = :n, sha256 = :h WHERE url = :o"),
                         {"n": nova_url, "h": imagem.sha256, "o": url})
            resultado["convertidas"].append(id_visita)
            if apagar_originais:
                origem.unlink()
                resultado["apagadas"].append(id_visita)
    return resultado


# ---------------------------------------------------------------------------------------------------------------------
def preencher_hashes(engine, dry_run: bool = False) -> Dict[str, int]:
    """
    Preenche sha256 NULL das linhas cujo arquivo ainda existe em disco. Atencao ao significado: grava o hash do arquivo
    COMO ESTA HOJE (nao prova que e o original); serve para detectar alteracoes DAQUI PARA A FRENTE.
    """
    resumo = {"servico_foto": 0, "comprovante": 0, "sync_arquivo": 0, "visita.arquivos_sha256": 0,
              "visita.assinatura_sha256": 0, "sem_arquivo": 0}
    campos_visita = ["odometro_inicio_url", "odometro_fim_url", "foto_inicio_ida_url", "foto_fim_ida_url",
                     "foto_inicio_volta_url", "foto_fim_volta_url"]
    with engine.begin() as conn:
        for tabela, pk in (("servico_foto", "id_foto"), ("comprovante", "id_comprovante"), ("sync_arquivo", "client_file_id")):
            for id_, url in conn.execute(text(f"SELECT {pk}, url FROM {tabela} WHERE sha256 IS NULL")).fetchall():
                dados = file_service.ler_arquivo_por_url(url)
                if dados is None:
                    resumo["sem_arquivo"] += 1
                    continue
                if not dry_run:
                    conn.execute(text(f"UPDATE {tabela} SET sha256 = :h WHERE {pk} = :i"),
                                 {"h": file_service.sha256_hex(dados), "i": id_})
                resumo[tabela] += 1
        colunas = ", ".join(["id_visita", "assinatura_url", "assinatura_sha256", "arquivos_sha256"] + campos_visita)
        eh_pg = engine.dialect.name == "postgresql"
        for linha in conn.execute(text(f"SELECT {colunas} FROM visita ORDER BY id_visita")).fetchall():
            id_visita, a_url, a_sha, arq_sha = linha[0], linha[1], linha[2], linha[3]
            if isinstance(arq_sha, str):
                arq_sha = json.loads(arq_sha)
            hashes = dict(arq_sha or {})
            mudou = False
            for campo, url in zip(campos_visita, linha[4:]):
                if url and campo not in hashes:
                    dados = file_service.ler_arquivo_por_url(url)
                    if dados is None:
                        resumo["sem_arquivo"] += 1
                    else:
                        hashes[campo] = file_service.sha256_hex(dados)
                        mudou = True
                        resumo["visita.arquivos_sha256"] += 1
            if mudou and not dry_run:
                expr = "CAST(:j AS jsonb)" if eh_pg else ":j"
                conn.execute(text(f"UPDATE visita SET arquivos_sha256 = {expr} WHERE id_visita = :i"),
                             {"j": json.dumps(hashes), "i": id_visita})
            if a_url and not a_sha:
                dados = file_service.ler_arquivo_por_url(a_url)
                if dados is None:
                    resumo["sem_arquivo"] += 1
                else:
                    if not dry_run:
                        conn.execute(text("UPDATE visita SET assinatura_sha256 = :h WHERE id_visita = :i"),
                                     {"h": file_service.sha256_hex(dados), "i": id_visita})
                    resumo["visita.assinatura_sha256"] += 1
    return resumo


# ---------------------------------------------------------------------------------------------------------------------
def _verificar(engine, incluir_campos: bool = True, incluir_payload: bool = True) -> int:
    """Somente leitura. Imprime so contagens e IDs. Retorna 1 se houver qualquer pendencia, 0 se tudo estiver cifrado."""
    pendencias = 0
    if incluir_campos:
        pend = verificar_campos(engine)
        print("Pendencias dos campos (tudo 0 = completo):", pend)
        pendencias += sum(pend.values())
    if incluir_payload:
        contagens, ids = verificar_payload_sync(engine)
        print("Pendencias do payload do sync (tudo 0 = completo):", contagens)
        if ids:
            print("client_event_id com pendencia ou anomalia:", ids)
        pendencias += sum(contagens.values())
    if pendencias:
        print("ATENCAO: ha valores em claro, anomalos (enc1: que nao decifra) ou cnpj_idx vazio; a migracao NAO esta "
              "completa. Rode o script sem --verificar para cifrar/corrigir.")
        return 1
    print("OK: nenhuma pendencia.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Cifra/protege os dados existentes (Confidencialidade e Integridade).")
    ap.add_argument("--dry-run", action="store_true", help="nao grava nada; mostra o que seria feito")
    ap.add_argument("--campos", action="store_true")
    ap.add_argument("--payload-sync", action="store_true",
                    help="cifra documento_cliente/nome_cliente em sync_evento.payload (nao exige a 0014)")
    ap.add_argument("--assinaturas", action="store_true")
    ap.add_argument("--hashes", action="store_true")
    ap.add_argument("--verificar", action="store_true",
                    help="SOMENTE LEITURA: lista pendencias de campos e payload; sai com codigo != 0 se houver "
                         "(combine com --campos ou --payload-sync para restringir)")
    ap.add_argument("--decifrar", action="store_true",
                    help="reverte campos e payload do sync para texto puro (rollback das 0011/0014); round-trip exato so "
                         "para valores string (nao-string do payload volta como texto JSON)")
    ap.add_argument("--apagar-originais", action="store_true")
    args = ap.parse_args()

    from app.db.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}  {'(DRY-RUN)' if args.dry_run else ''}")
    so_campos = args.campos and not args.payload_sync
    so_payload = args.payload_sync and not args.campos
    if args.verificar:
        return _verificar(engine, incluir_campos=not so_payload, incluir_payload=not so_campos)
    if args.decifrar:
        anomalias: List[str] = []
        if not so_payload:
            print("Campos decifrados:", decifrar_campos(engine, args.dry_run))
        if not so_campos:
            print("Payload do sync decifrado:", decifrar_payload_sync(engine, args.dry_run, anomalias))
            if anomalias:
                print("ATENCAO: enc1: que nao decifra (mantido como esta) nos client_event_id:", anomalias)
        return 0
    tudo = not (args.campos or args.payload_sync or args.assinaturas or args.hashes)
    fazer_campos = tudo or args.campos
    fazer_payload = tudo or args.payload_sync
    if fazer_campos:  # ANTES de qualquer escrita: sem a 0014 o valor cifrado nao cabe em VARCHAR (H1 sozinho: --payload-sync)
        ruins = colunas_nao_text(engine)
        if ruins:
            print("ABORTADO: colunas ainda nao sao TEXT (aplique a migracao 0014 antes):", ruins)
            print("Para cifrar SOMENTE o payload do sync (H1, sem DDL), use --payload-sync.")
            return 2
        print("Campos cifrados:", cifrar_campos(engine, args.dry_run))
    if fazer_payload:
        anomalias = []
        print("Payload do sync cifrado:", cifrar_payload_sync(engine, args.dry_run, anomalias))
        if anomalias:
            print("ATENCAO: enc1: que nao decifrava (cifrado por cima) nos client_event_id:", anomalias)
    if tudo or args.assinaturas:
        r = converter_assinaturas(engine, args.dry_run, args.apagar_originais)
        print("Assinaturas:", {k: len(v) for k, v in r.items()}, "| ausentes (visitas):", r["ausentes"])
    if tudo or args.hashes:
        print("Hashes:", preencher_hashes(engine, args.dry_run))
    if not args.dry_run and (fazer_campos or fazer_payload):
        codigo = _verificar(engine, incluir_campos=fazer_campos, incluir_payload=fazer_payload)
        if codigo == 0 and fazer_campos:
            print("Aplique 0012_cnpj_idx_obrigatorio.sql (se ainda nao aplicada) e defina "
                  "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false.")
        return codigo
    return 0


if __name__ == "__main__":
    sys.exit(main())
