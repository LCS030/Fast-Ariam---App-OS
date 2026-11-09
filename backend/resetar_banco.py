"""
Apaga TODAS as tabelas, recria o schema e semeia o administrador. Script DESTRUTIVO, somente para dev/teste (SEG-05).

Travas:
  1. Recusa com ENV=production.
  2. Exige DATABASE_URL definida (nunca roda "sem banco explícito").
  3. Recusa banco remoto (host fora de localhost/127.0.0.1/::1) sem --allow-remote.
  4. Exige confirmação explícita: --yes, ou digitar o nome do banco exibido.

Uso:
  python resetar_banco.py                 # pede para digitar o nome do banco
  python resetar_banco.py --yes           # sem prompt (somente banco local)
  python resetar_banco.py --yes --allow-remote   # banco de dev hospedado fora da máquina (cuidado)
"""
import argparse
import os
import sys
from typing import Callable, List, Optional

from sqlalchemy.engine import make_url

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}


class ResetBloqueado(Exception):
    """Reset recusado por uma trava de segurança."""


def validar_reset(env: str, database_url: Optional[str], yes: bool, allow_remote: bool,
                  pedir_confirmacao: Callable[[str], str] = input) -> str:
    """
    Aplica as travas e retorna o nome do banco-alvo. Levanta ResetBloqueado se alguma trava falhar.
    Função pura (sem tocar no banco) para ser testável.
    """
    if (env or "").strip().lower() in ("production", "prod"):
        raise ResetBloqueado("Recusado: ENV=production. Este script nunca roda em produção.")

    if not database_url:
        raise ResetBloqueado("Recusado: DATABASE_URL não definida. Informe explicitamente o banco local de desenvolvimento.")

    url = make_url(database_url)
    nome_banco = url.database or ""
    eh_sqlite = url.get_backend_name() == "sqlite"
    host = (url.host or "").lower()

    if not eh_sqlite and host not in HOSTS_LOCAIS and not allow_remote:
        raise ResetBloqueado(
            f"Recusado: o banco '{nome_banco}' está em host remoto ({host or 'desconhecido'}). "
            "Use um PostgreSQL local; se for um banco remoto de DESENVOLVIMENTO, passe --allow-remote."
        )

    if not yes:
        digitado = pedir_confirmacao(
            f"Isto APAGARÁ todos os dados do banco '{nome_banco}' (host: {host or 'arquivo local'}).\n"
            f"Digite o nome do banco para confirmar: "
        ).strip()
        if digitado != nome_banco or not nome_banco:
            raise ResetBloqueado("Confirmação não confere. Nada foi alterado.")

    return nome_banco


def resetar_tudo():
    # Importa só depois das travas (importar o engine não conecta, mas evita qualquer efeito colateral antes).
    from app.db.database import engine, Base
    from seed import importar_modelos, semear_banco

    importar_modelos()

    print("Removendo todas as tabelas...")
    Base.metadata.drop_all(bind=engine)

    print("Recriando tabelas...")
    Base.metadata.create_all(bind=engine)

    print("Semeando o administrador...")
    semear_banco()

    print("Banco de dados resetado.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reseta o banco de DESENVOLVIMENTO (destrutivo).")
    parser.add_argument("--yes", action="store_true", help="Confirma sem digitar o nome do banco.")
    parser.add_argument("--allow-remote", action="store_true", help="Permite banco fora de localhost (dev remoto).")
    args = parser.parse_args(argv)

    from app.core.config import ENV
    try:
        validar_reset(ENV, os.getenv("DATABASE_URL"), args.yes, args.allow_remote)
    except ResetBloqueado as erro:
        print(str(erro), file=sys.stderr)
        return 1

    resetar_tudo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
