"""
Redefine a senha de um administrador (ou cria um, com --criar). Uso pelo terminal, a partir de backend/:

    python scripts/redefinir_senha_admin.py                       # lista os admins e pergunta qual redefinir
    python scripts/redefinir_senha_admin.py --email admin@x.com   # redefine esse admin
    python scripts/redefinir_senha_admin.py --email novo@x.com --criar [--cnpj 11.111.111/0001-11]

- Usa o DATABASE_URL do .env (o MESMO banco da API; neste projeto, o Supabase de producao).
- A senha e pedida sem aparecer na tela (ou via variavel de ambiente NOVA_SENHA, se preferir).
- Usa o mesmo hash (bcrypt) e a mesma politica de senha da API (8 a 72 bytes).
- Altera SOMENTE tecnico.password_hash (e is_active=true no admin escolhido). Nunca imprime hash.
- Pede confirmacao antes de gravar (use --sim para pular a confirmacao).
- Nao ha sessao a revogar: os tokens antigos expiram sozinhos (e a API revalida o usuario a cada requisicao).
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

# permite rodar de qualquer pasta: backend/ precisa estar no sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib  # noqa: E402
import pkgutil  # noqa: E402

from sqlalchemy import func  # noqa: E402

import app.models as _pacote_models  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.schemas.token import validar_forca_senha  # noqa: E402

# Tecnico tem relationship com OrdemServico: todos os modelos precisam estar registrados (como no seed.py).
for _m in pkgutil.iter_modules(_pacote_models.__path__):
    importlib.import_module(f"{_pacote_models.__name__}.{_m.name}")
from app.models.tecnico import Tecnico  # noqa: E402

CNPJ_MARCADOR = "00.000.000/0000-00"  # mesmo marcador do seed.py (UNIQUE)
CPF_MARCADOR = "000.000.000-00"


def _ler_senha() -> str:
    senha = os.getenv("NOVA_SENHA")
    if senha:
        return validar_forca_senha(senha)
    while True:
        s1 = getpass.getpass("Nova senha (8 a 72 bytes): ")
        try:
            validar_forca_senha(s1)
        except ValueError as exc:
            print(f"  {exc}")
            continue
        if s1 != getpass.getpass("Repita a senha: "):
            print("  As senhas nao conferem.")
            continue
        return s1


def _listar_admins(db) -> list:
    admins = db.query(Tecnico).filter(Tecnico.role == "tecnico").order_by(Tecnico.id_tecnico).all()
    if not admins:
        print("Nenhum administrador encontrado.")
    for a in admins:
        print(f"  id={a.id_tecnico}  email={a.email}  ativo={'sim' if a.is_active else 'NAO'}  nome={a.nome}")
    return admins


def main() -> int:
    ap = argparse.ArgumentParser(description="Redefine a senha de um administrador.")
    ap.add_argument("--email", help="e-mail do admin (se omitido, lista e pergunta)")
    ap.add_argument("--criar", action="store_true", help="cria o admin se o e-mail nao existir")
    ap.add_argument("--cnpj", default=CNPJ_MARCADOR, help="CNPJ do admin criado (UNIQUE; padrao: marcador do seed)")
    ap.add_argument("--sim", action="store_true", help="nao pedir confirmacao")
    args = ap.parse_args()

    print(f"Banco: {engine.url.render_as_string(hide_password=True)}")
    db = SessionLocal()
    try:
        print("Administradores atuais:")
        admins = _listar_admins(db)

        email = (args.email or "").strip().lower()
        if not email:
            if not admins:
                print("Use --email NOVO --criar para criar o primeiro admin.")
                return 1
            email = input("E-mail do admin a redefinir: ").strip().lower()

        alvo = db.query(Tecnico).filter(func.lower(Tecnico.email) == email).first()
        if alvo is None and not args.criar:
            print(f"ERRO: nao existe usuario com o e-mail {email}. Use --criar para cria-lo.")
            return 1
        if alvo is not None and alvo.role != "tecnico":
            print(f"ERRO: {email} existe, mas NAO e admin (papel '{alvo.role}'). Nada foi alterado.")
            return 1

        senha = _ler_senha()
        acao = "CRIAR admin" if alvo is None else "REDEFINIR a senha (e ativar) do admin"
        if not args.sim and input(f"Confirma {acao} {email}? [s/N] ").strip().lower() not in ("s", "sim", "y", "yes"):
            print("Cancelado. Nada foi alterado.")
            return 1

        if alvo is None:
            if db.query(Tecnico).filter(Tecnico.cnpj == args.cnpj).first():
                print(f"ERRO: o CNPJ {args.cnpj} ja esta em uso (UNIQUE). Informe outro com --cnpj.")
                return 1
            db.add(Tecnico(nome="Administrador", cpf=CPF_MARCADOR, cnpj=args.cnpj, email=email,
                           password_hash=hash_password(senha), role="tecnico", is_active=True))
        else:
            alvo.password_hash = hash_password(senha)
            alvo.is_active = True
        db.commit()
        print(f"Pronto. Faca login em /api/auth/login com {email} e a senha informada.")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"ERRO: {type(exc).__name__}: {exc}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
