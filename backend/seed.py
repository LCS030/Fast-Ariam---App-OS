# seed.py
from app.db.database import SessionLocal, engine, Base
# Importamos todos os modelos para garantir que as tabelas sejam criadas
from app.models import tecnico, cliente, chamado, visita, servico_equipamento, material, comprovante, servico_defeito, \
    servico_foto
from app.core.security import hash_password


def semear_banco():
    print("⏳ Conectando ao banco de dados e criando tabelas...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    email_admin = "admin@fastariam.com"

    # Verifica se já existe um admin
    admin_existente = db.query(tecnico.Tecnico).filter(tecnico.Tecnico.email == email_admin).first()

    if not admin_existente:
        print("🌱 Criando o primeiro Administrador Mestre...")
        novo_admin = tecnico.Tecnico(
            nome="Administrador Mestre",
            cpf="000.000.000-00",
            cnpj="00.000.000/0000-00",
            email=email_admin,
            password_hash=hash_password("admin123"),  # Senha padrão inicial
            role="admin",
            is_active=True
        )
        db.add(novo_admin)
        db.commit()
        print(f"✅ Sucesso! E-mail: {email_admin} | Senha: admin123")
    else:
        print("ℹ️ O banco já possui o Administrador Mestre.")

    db.close()


if __name__ == "__main__":
    semear_banco()