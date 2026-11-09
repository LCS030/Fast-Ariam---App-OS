"""
Backup do banco (PostgreSQL/Supabase) e dos arquivos enviados. Uso, a partir de backend/:

    python scripts/backup_banco.py                      # backup completo em backups/AAAAMMDD-HHMMSS/
    python scripts/backup_banco.py --sem-arquivos       # so o banco
    python scripts/backup_banco.py --saida D:/cofre     # outra pasta de destino
    python scripts/backup_banco.py --verificar backups/20261108-120000   # confere o manifesto (SHA-256 e linhas)

O que gera (tudo SOMENTE LEITURA no banco: transacao READ ONLY / REPEATABLE READ = retrato consistente):
  * Se `pg_dump` existir no PATH: banco.dump (formato custom, restaura com `pg_restore`).
  * Sempre: dados/<tabela>.jsonl.gz (uma linha JSON por registro) + estrutura.json (colunas, constraints, indices,
    enums) -> funciona mesmo sem pg_dump (caso desta maquina). O DDL completo continua nas migrations/.
  * arquivos.zip com static/uploads e static/assinaturas (a menos que --sem-arquivos).
  * manifesto.json: data/hora, host (SEM senha), contagem de linhas por tabela e SHA-256 de cada arquivo gerado.

ATENCAO: o backup contem dados pessoais (CPF, dados bancarios, assinaturas). A pasta backups/ esta no .gitignore;
guarde a copia em local protegido. As chaves (DATA_ENCRYPTION_KEY, INDEX_KEY, INTEGRITY_KEY) NAO entram no backup:
guarde-as a parte (cofre de senhas); sem a DATA_ENCRYPTION_KEY os campos cifrados nao sao recuperaveis.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]  # backend/
load_dotenv(RAIZ / ".env")

PASTAS_ARQUIVOS = ["static/uploads", "static/assinaturas"]
LOTE = 2000


def _url_psycopg() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        sys.exit("ERRO: DATABASE_URL nao definida (.env).")
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _host_seguro(url: str) -> str:
    p = urlparse(url)
    return f"{p.hostname}:{p.port or 5432}/{(p.path or '/').lstrip('/')}"


def _json_default(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"__bytes_hex__": bytes(v).hex()}
    return str(v)


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _estrutura(cur) -> dict:
    cur.execute("""SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
                   FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position""")
    colunas: dict = {}
    for t, c, tipo, udt, nul, dflt in cur.fetchall():
        colunas.setdefault(t, []).append({"coluna": c, "tipo": tipo, "udt": udt, "nulo": nul == "YES", "default": dflt})
    cur.execute("""SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
                   FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1, 2""")
    constraints = [{"tabela": t, "nome": n, "definicao": d} for t, n, d in cur.fetchall()]
    cur.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1, 2")
    indices = [{"tabela": t, "nome": n, "definicao": d} for t, n, d in cur.fetchall()]
    cur.execute("""SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
                   FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid
                   JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' GROUP BY t.typname""")
    enums = {n: list(v) for n, v in cur.fetchall()}
    return {"colunas": colunas, "constraints": constraints, "indices": indices, "enums": enums}


def _exportar_tabelas(conn, destino: Path) -> dict:
    """Exporta cada tabela de public para dados/<tabela>.jsonl.gz e confere a contagem. Retorna {tabela: linhas}."""
    import psycopg2.extras  # noqa: F401  (garante o modulo extras carregado)

    dados = destino / "dados"
    dados.mkdir(parents=True, exist_ok=True)
    cur = conn.cursor()
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    tabelas = [r[0] for r in cur.fetchall()]
    contagens: dict = {}
    for t in tabelas:
        cur.execute(f'SELECT count(*) FROM public."{t}"')
        esperado = cur.fetchone()[0]
        cur.execute(f'SELECT * FROM public."{t}" LIMIT 0')
        colunas = [d[0] for d in cur.description]
        nome_cursor = f"bk_{t}"[:60]
        with conn.cursor(name=nome_cursor) as stream:  # cursor no servidor: nao carrega a tabela inteira na memoria
            stream.itersize = LOTE
            stream.execute(f'SELECT * FROM public."{t}"')
            gravadas = 0
            caminho = dados / f"{t}.jsonl.gz"
            with gzip.open(caminho, "wt", encoding="utf-8", newline="\n") as f:
                for linha in stream:
                    f.write(json.dumps(dict(zip(colunas, linha)), default=_json_default, ensure_ascii=False) + "\n")
                    gravadas += 1
        if gravadas != esperado:
            sys.exit(f"ERRO: tabela {t}: count(*)={esperado} mas {gravadas} linhas exportadas. Backup invalido.")
        contagens[t] = gravadas
        print(f"  {t}: {gravadas} linhas")
    return contagens


def _zip_arquivos(destino: Path) -> int:
    total = 0
    caminho = destino / "arquivos.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in PASTAS_ARQUIVOS:
            pasta = RAIZ / rel
            if not pasta.is_dir():
                continue
            for arq in sorted(pasta.rglob("*")):
                if arq.is_file() and arq.name != ".gitkeep":
                    z.write(arq, arq.relative_to(RAIZ).as_posix())
                    total += 1
    print(f"  arquivos.zip: {total} arquivos")
    return total


def _pg_dump(url: str, destino: Path) -> bool:
    exe = shutil.which("pg_dump")
    if not exe:
        print("  pg_dump nao encontrado no PATH: seguindo so com o export em JSONL (suficiente para restaurar os dados).")
        return False
    saida = destino / "banco.dump"
    r = subprocess.run([exe, "--format=custom", "--no-owner", "--no-privileges", "--schema=public", f"--file={saida}", url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("  AVISO: pg_dump falhou (o export JSONL continua valido):", r.stderr.strip().splitlines()[-1:])
        saida.unlink(missing_ok=True)
        return False
    print(f"  banco.dump: {saida.stat().st_size} bytes")
    return True


def verificar(pasta: Path) -> int:
    man = json.loads((pasta / "manifesto.json").read_text(encoding="utf-8"))
    erros = 0
    for rel, esperado in man["sha256"].items():
        arq = pasta / rel
        if not arq.exists():
            print(f"FALTA   {rel}")
            erros += 1
        elif _sha256(arq) != esperado:
            print(f"DIVERGE {rel}")
            erros += 1
    for t, n in man["tabelas"].items():
        with gzip.open(pasta / "dados" / f"{t}.jsonl.gz", "rt", encoding="utf-8") as f:
            reais = sum(1 for _ in f)
        if reais != n:
            print(f"LINHAS  {t}: manifesto={n} arquivo={reais}")
            erros += 1
    print("Backup INTEGRO." if not erros else f"{erros} problema(s) encontrado(s).")
    return 1 if erros else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Backup do banco e dos arquivos do Fast Ariam.")
    ap.add_argument("--saida", help="pasta base de destino (padrao: backend/backups)")
    ap.add_argument("--sem-arquivos", action="store_true", help="nao inclui static/uploads e static/assinaturas")
    ap.add_argument("--verificar", metavar="PASTA", help="apenas confere um backup existente")
    args = ap.parse_args()

    if args.verificar:
        return verificar(Path(args.verificar))

    import psycopg2

    url = _url_psycopg()
    base = Path(args.saida) if args.saida else RAIZ / "backups"
    destino = base / datetime.now().strftime("%Y%m%d-%H%M%S")
    destino.mkdir(parents=True, exist_ok=False)
    print(f"Backup de {_host_seguro(url)} -> {destino}")

    conn = psycopg2.connect(url, sslmode=os.getenv("DB_SSLMODE", "require"))
    try:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)  # retrato unico e nenhuma escrita possivel
        cur = conn.cursor()
        (destino / "estrutura.json").write_text(
            json.dumps(_estrutura(cur), ensure_ascii=False, indent=2), encoding="utf-8")
        tabelas = _exportar_tabelas(conn, destino)
    finally:
        conn.rollback()
        conn.close()

    usou_pg_dump = _pg_dump(url, destino)
    n_arquivos = 0 if args.sem_arquivos else _zip_arquivos(destino)

    sha = {p.relative_to(destino).as_posix(): _sha256(p) for p in sorted(destino.rglob("*")) if p.is_file()}
    manifesto = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "origem": _host_seguro(url),
        "tabelas": tabelas,
        "arquivos_incluidos": n_arquivos,
        "pg_dump": usou_pg_dump,
        "sha256": sha,
    }
    (destino / "manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Concluido: {sum(tabelas.values())} linhas em {len(tabelas)} tabelas. Conferindo manifesto...")
    return verificar(destino)


if __name__ == "__main__":
    sys.exit(main())
