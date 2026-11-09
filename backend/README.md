# Backend do Projeto Fast Ariam

API FastAPI do sistema de gerenciamento de Ordens de Serviço da Fast Ariam. Banco: **PostgreSQL** (gerenciado pelo
Supabase), acessado via SQLAlchemy + `psycopg2`. O contrato oficial está em `PRD-Fast-Ariam.md` e `SDD-Fast-Ariam.md`
(raiz do repositório).

## Como rodar

1. **Ambiente virtual (recomendado), Python 3.14:**
    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

2. **Dependências:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Configuração:** copie `.env.example` para `.env` e preencha (o `.env` não é versionado).

   | Variável | Obrigatória | Padrão | Descrição |
   |---|---|---|---|
   | `SECRET_KEY` | Sim | — | Assinatura do JWT. Sem ela a API não inicia. |
   | `DATABASE_URL` | Sim | — | `postgresql+psycopg2://USUARIO:SENHA@HOST:5432/BANCO` |
   | `ENV` | Não | `development` | `development`, `test` ou `production` (ver abaixo). |
   | `ALGORITHM` | Não | `HS256` | Somente HS256/HS384/HS512. |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | Não | `30` | Validade do token (não há refresh token). |
   | `CORS_ORIGINS` | Sim em produção | localhost em dev | Origens do painel, separadas por vírgula. `*` é recusado. |
   | `AUTO_CREATE_TABLES` | Não | `false` | `true` cria as tabelas no startup (**apenas dev/teste**). |
   | `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | Não | `admin@fastariam.com` / gerada | Usadas só pelo `seed.py`. |

   Com `ENV=production`: `CORS_ORIGINS` é obrigatória, `AUTO_CREATE_TABLES=true` é recusada e `resetar_banco.py` não executa.

4. **Banco de dados:** o schema de produção deve ser criado/alterado por **migrações versionadas** (pasta `migrations/`,
   mantida pelo DBA). Somente em desenvolvimento local você pode usar `AUTO_CREATE_TABLES=true` para criar as tabelas
   no startup. Nunca habilite isso contra o banco de produção.

5. **Primeiro administrador:**
    ```bash
    python seed.py
    ```
   Se `SEED_ADMIN_PASSWORD` não estiver definida, uma senha aleatória é gerada e exibida **uma única vez**. Troque-a
   no primeiro acesso (`PATCH /api/tecnicos/me/password`). Não há senha padrão no código.

6. **Servidor:**
    ```bash
    uvicorn app.main:app --reload
    ```

## Acesso à API

* **Servidor local:** `http://127.0.0.1:8000`
* **Swagger:** `http://127.0.0.1:8000/docs`

## Autenticação (resumo)

* `POST /api/auth/login` (form `username`=e-mail, `password`) retorna o Bearer JWT. E-mail inexistente, senha errada e
  usuário inativo retornam sempre `401 "Email ou senha incorretos"`.
* `GET /api/auth/me` retorna `{id_tecnico, nome, email, role, is_active}` (sem dados bancários).
* A cada requisição o usuário é consultado no banco: técnico/admin inativo ou removido recebe `401` mesmo com token
  válido, e o papel (`role`) é o do banco.

## Testes

```bash
pytest
```

Os testes configuram **SQLite temporário** e uma `SECRET_KEY` de teste em `tests/conftest.py` **antes** de importar a
aplicação. Nunca usam o `DATABASE_URL` do `.env` (nem tocam em banco real).

## Reset do banco (somente dev)

`python resetar_banco.py` apaga todas as tabelas. Recusa `ENV=production`, exige `DATABASE_URL` explícita, recusa
host remoto sem `--allow-remote` e exige `--yes` ou a digitação do nome do banco.

## Observações

* A pasta `mysql/` é **legada** (script do MySQL/XAMPP da fase de protótipo); o projeto usa PostgreSQL e ela não é
  usada pela aplicação.
* Arquivos enviados ainda são servidos de `/static` (disco local, público). A migração para Supabase Storage com bucket
  privado e URLs assinadas (SDD seção 9, SEG-09) está **pendente**.
