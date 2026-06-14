from app.db.database import engine, Base
# Importar todos os modelos para ele saber o que apagar/criar
from app.models import tecnico, cliente, chamado, visita, servico_equipamento, material, comprovante, servico_defeito, \
    servico_foto, pausa
from seed import semear_banco


def resetar_tudo():
    print("🧨 Destruindo todas as tabelas e zerando os IDs...")
    Base.metadata.drop_all(bind=engine)

    print("🏗️ Recriando tabelas limpas...")
    Base.metadata.create_all(bind=engine)

    print("🌱 Semeando o banco novamente...")
    semear_banco()

    print("✅ Banco de dados resetado com sucesso! Pronto para testes.")


if __name__ == "__main__":
    resetar_tudo()