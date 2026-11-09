"""
Copia as fotos, comprovantes e assinaturas (.enc) do DISCO LOCAL para o bucket PRIVADO do Supabase Storage.

    python scripts/migrar_arquivos_para_storage.py --dry-run          # so relata o que faria (nao grava nada)
    python scripts/migrar_arquivos_para_storage.py                    # copia e CONFERE cada arquivo
    python scripts/migrar_arquivos_para_storage.py --apagar-locais    # alem disso, apaga a copia local CONFIRMADA no bucket
    python scripts/migrar_arquivos_para_storage.py --incluir-orfaos   # tambem sobe arquivos que nenhuma linha do banco referencia

Rodar a partir de backend/. Exige SUPABASE_URL e SUPABASE_SERVICE_KEY (e STORAGE_BUCKET) no .env. Faca backup antes
(scripts/backup_banco.py); o backup inclui os arquivos locais.

O que garante a migracao:
  * A referencia no banco (`/static/uploads/<nome>`, `/static/assinaturas/<nome>.enc`) NAO muda: o objeto vai para
    `uploads/<nome>` / `assinaturas/<nome>` do bucket. Por isso nenhuma linha e atualizada e os selos de integridade
    continuam validos.
  * Antes de subir, compara o SHA-256 do arquivo local com o gravado no banco (quando existe). Divergente => NAO sobe e e
    reportado (o arquivo mudou depois de gravado).
  * Nunca sobrescreve: objeto ja existente com o mesmo conteudo => "ja_no_bucket"; com conteudo DIFERENTE => "conflito".
  * Depois de subir, BAIXA o objeto e confere byte a byte com o local. So entao conta como "migrado".
  * Assinatura em claro (nao .enc) NAO sobe: rode antes `python scripts/cifrar_dados_existentes.py --assinaturas`.
  * Relatorio de ausentes (referenciados no banco sem arquivo), orfaos (sem referencia) e divergentes.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core import config  # noqa: E402
from app.core.crypto import ErroDecifragem, decifrar_bytes  # noqa: E402
from app.services import file_service  # noqa: E402
from app.services.storage_service import SupabaseStorage  # noqa: E402

CAMPOS_FOTO_VISITA = ["odometro_inicio_url", "odometro_fim_url", "foto_inicio_ida_url", "foto_fim_ida_url",
                      "foto_inicio_volta_url", "foto_fim_volta_url"]


def referencias_do_banco(engine) -> Dict[Tuple[str, str], Optional[str]]:
    """{(area, nome): sha256 esperado do conteudo ORIGINAL (None se nao ha hash gravado)} de tudo que o banco referencia."""
    refs: Dict[Tuple[str, str], Optional[str]] = {}

    def anotar(url: Optional[str], sha: Optional[str]) -> None:
        ref = file_service._referencia(url)
        if ref is not None and (ref not in refs or not refs[ref]):
            refs[ref] = sha

    with engine.connect() as c:
        for tabela in ("servico_foto", "comprovante", "sync_arquivo"):
            for url, sha in c.execute(text(f"SELECT url, sha256 FROM {tabela}")).fetchall():
                anotar(url, sha)
        cols = ", ".join(["assinatura_url", "assinatura_sha256", "arquivos_sha256"] + CAMPOS_FOTO_VISITA)
        for linha in c.execute(text(f"SELECT {cols} FROM visita")).fetchall():
            anotar(linha[0], linha[1])
            hashes = linha[2]
            if isinstance(hashes, str):
                hashes = json.loads(hashes)
            for campo, url in zip(CAMPOS_FOTO_VISITA, linha[3:]):
                anotar(url, (hashes or {}).get(campo))
    return refs


def arquivos_locais() -> List[Tuple[str, str, Path]]:
    achados = []
    for area, pasta in (("uploads", file_service.UPLOAD_DIRECTORY), ("assinaturas", file_service.ASSINATURA_DIRECTORY)):
        if pasta.is_dir():
            for p in sorted(pasta.iterdir()):
                if p.is_file() and p.name != ".gitkeep" and not p.name.endswith(".part"):
                    achados.append((area, p.name, p))
    return achados


def content_type(area: str, nome: str, dados: bytes) -> str:
    if area == "assinaturas" or nome.endswith(".enc"):
        return "application/octet-stream"
    return file_service.tipo_mime_da_imagem(dados)


def migrar(engine, storage, *, dry_run: bool = False, apagar_locais: bool = False, incluir_orfaos: bool = False) -> dict:
    refs = referencias_do_banco(engine)
    rel: Dict[str, list] = {k: [] for k in ("migrado", "ja_no_bucket", "conflito", "divergente_do_banco", "orfao",
                                            "assinatura_em_claro", "ilegivel", "ausente", "apagado_local")}
    vistos = set()
    for area, nome, caminho in arquivos_locais():
        ref = (area, nome)
        vistos.add(ref)
        rotulo = f"{area}/{nome}"
        local = caminho.read_bytes()
        if ref not in refs and not incluir_orfaos:
            rel["orfao"].append(rotulo)
            continue
        if area == "assinaturas" and not nome.endswith(".enc"):
            rel["assinatura_em_claro"].append(rotulo)
            continue
        esperado = refs.get(ref)
        original = local
        if nome.endswith(".enc"):
            try:
                original = decifrar_bytes(local, file_service.CONTEXTO_ASSINATURA)
            except ErroDecifragem:
                rel["ilegivel"].append(rotulo)
                continue
        if esperado and file_service.sha256_hex(original) != esperado:
            rel["divergente_do_banco"].append(rotulo)
            continue
        remoto = storage.get(area, nome)
        if remoto is not None:
            (rel["ja_no_bucket"] if remoto == local else rel["conflito"]).append(rotulo)
        else:
            if dry_run:
                rel["migrado"].append(rotulo)
                continue
            storage.put(area, nome, local, content_type(area, nome, original))
            if storage.get(area, nome) != local:  # conferencia byte a byte DEPOIS de subir
                raise RuntimeError(f"Conferencia falhou apos o upload de {rotulo}; nada foi apagado.")
            rel["migrado"].append(rotulo)
        if apagar_locais and not dry_run and rotulo in (rel["migrado"] + rel["ja_no_bucket"]):
            caminho.unlink()
            rel["apagado_local"].append(rotulo)
    for ref in sorted(set(refs) - vistos):
        if storage.get(*ref) is None:  # nem local nem no bucket
            rel["ausente"].append(f"{ref[0]}/{ref[1]}")
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description="Migra os arquivos do disco local para o Supabase Storage privado.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apagar-locais", action="store_true", help="apaga a copia local so DEPOIS de confirmada no bucket")
    ap.add_argument("--incluir-orfaos", action="store_true")
    args = ap.parse_args()

    if config.STORAGE_BACKEND != "supabase":
        print("ERRO: defina SUPABASE_URL e SUPABASE_SERVICE_KEY no backend/.env (a chave de servico fica so no backend).")
        return 2
    from app.db.database import engine

    storage = SupabaseStorage(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.STORAGE_BUCKET)
    print(f"Bucket: {config.STORAGE_BUCKET} em {config.SUPABASE_URL}  {'(DRY-RUN)' if args.dry_run else ''}")
    rel = migrar(engine, storage, dry_run=args.dry_run, apagar_locais=args.apagar_locais,
                 incluir_orfaos=args.incluir_orfaos)
    for chave, itens in rel.items():
        print(f"  {chave:20s} {len(itens):4d}" + (f"   {itens}" if itens and chave not in ("migrado", "ja_no_bucket") else ""))
    pasta = Path("backups")
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"migracao_storage_{datetime.now():%Y%m%d-%H%M%S}.json"
    arq.write_text(json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Relatorio: {arq}")
    problemas = sum(len(rel[k]) for k in ("conflito", "divergente_do_banco", "assinatura_em_claro", "ilegivel", "ausente"))
    if problemas:
        print(f"ATENCAO: {problemas} item(ns) exigem decisao. Nada foi sobrescrito nem apagado por causa deles.")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
