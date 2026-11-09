"""
Migra os dados JA EXISTENTES para o modelo de seguranca (Confidencialidade + Integridade). Uso, a partir de backend/:

    python scripts/cifrar_dados_existentes.py --dry-run          # so conta o que seria feito (nao grava nada)
    python scripts/cifrar_dados_existentes.py                    # campos + assinaturas + hashes
    python scripts/cifrar_dados_existentes.py --campos           # so cifra os campos sensiveis e preenche tecnico.cnpj_idx
    python scripts/cifrar_dados_existentes.py --assinaturas      # converte assinaturas em claro para .enc (AES-256-GCM)
    python scripts/cifrar_dados_existentes.py --hashes           # preenche sha256 das fotos/comprovantes que existem em disco
    python scripts/cifrar_dados_existentes.py --decifrar         # REVERTE os campos para texto puro (pre-requisito de 0011_rollback)
    ... --apagar-originais                                       # (com --assinaturas) apaga a assinatura em claro apos conferir o .enc

PRE-REQUISITOS: backup (scripts/backup_banco.py) e migracoes 0010 e 0011 aplicadas. Usa o DATABASE_URL do .env (o MESMO
banco da API) e as chaves do .env (DATA_ENCRYPTION_KEY, INDEX_KEY). E IDEMPOTENTE: valores que ja comecam com "enc1:" e
arquivos que ja sao .enc sao ignorados; pode ser repetido. Cada tabela e gravada em UMA transacao (tudo ou nada).
Nunca imprime valores sensiveis, apenas contagens e IDs.

Depois de rodar sem erros: aplique 0012_cnpj_idx_obrigatorio.sql e defina ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false no .env.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core import crypto  # noqa: E402
from app.services import file_service  # noqa: E402

# tabela -> (coluna da chave primaria, [colunas cifradas])
CAMPOS_CIFRADOS = {
    "tecnico": ("id_tecnico", ["cnpj", "cpf", "telefone", "banco", "agencia", "conta", "pix"]),
    "visita": ("id_visita", ["documento_cliente"]),
}


def _contexto(tabela: str, coluna: str) -> str:
    return f"{tabela}.{coluna}"


def _indice_cnpj(cnpj_claro: str) -> str:
    return crypto.indice_cego(re.sub(r"\D", "", cnpj_claro or ""), "tecnico.cnpj")


# ---------------------------------------------------------------------------------------------------------------------
def cifrar_campos(engine, dry_run: bool = False) -> Dict[str, int]:
    """Cifra tecnico.* e visita.documento_cliente e preenche tecnico.cnpj_idx. Retorna {tabela.coluna: n_cifrados}."""
    resumo: Dict[str, int] = {}
    with engine.begin() as conn:
        for tabela, (pk, colunas) in CAMPOS_CIFRADOS.items():
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
        if dry_run:
            conn.rollback()
    return resumo


def decifrar_campos(engine, dry_run: bool = False) -> Dict[str, int]:
    """Reverte para texto puro (pre-requisito do 0011_rollback.sql). Mantem cnpj_idx."""
    resumo: Dict[str, int] = {}
    with engine.begin() as conn:
        for tabela, (pk, colunas) in CAMPOS_CIFRADOS.items():
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
        if dry_run:
            conn.rollback()
    return resumo


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
def main() -> int:
    ap = argparse.ArgumentParser(description="Cifra/protege os dados existentes (Confidencialidade e Integridade).")
    ap.add_argument("--dry-run", action="store_true", help="nao grava nada; mostra o que seria feito")
    ap.add_argument("--campos", action="store_true")
    ap.add_argument("--assinaturas", action="store_true")
    ap.add_argument("--hashes", action="store_true")
    ap.add_argument("--decifrar", action="store_true", help="reverte os campos para texto puro (rollback da 0011)")
    ap.add_argument("--apagar-originais", action="store_true")
    args = ap.parse_args()

    from app.db.database import engine

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}  {'(DRY-RUN)' if args.dry_run else ''}")
    if args.decifrar:
        print("Campos decifrados:", decifrar_campos(engine, args.dry_run))
        return 0
    tudo = not (args.campos or args.assinaturas or args.hashes)
    if tudo or args.campos:
        print("Campos cifrados:", cifrar_campos(engine, args.dry_run))
    if tudo or args.assinaturas:
        r = converter_assinaturas(engine, args.dry_run, args.apagar_originais)
        print("Assinaturas:", {k: len(v) for k, v in r.items()}, "| ausentes (visitas):", r["ausentes"])
    if tudo or args.hashes:
        print("Hashes:", preencher_hashes(engine, args.dry_run))
    if not args.dry_run and (tudo or args.campos):
        pend = verificar_campos(engine)
        print("Pendencias de verificacao (tudo 0 = completo):", pend)
        if any(pend.values()):
            print("ATENCAO: ainda ha valores em claro ou cnpj_idx vazio; NAO aplique a 0012 nem desligue o modo legado.")
            return 1
        print("OK: nenhum valor em claro. Aplique 0012_cnpj_idx_obrigatorio.sql e defina "
              "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
