# FAST Gôndolas & Check-outs — Frontend & Integração FastAPI

Sistema completo de Gestão de Ordens de Serviço, Deslocamento e Atendimento Técnico para **FAST Gôndolas & Check-outs**, integrado com o backend Python FastAPI.

---

## 🚀 Como Executar Localmente

### 1. Pré-requisitos
- **Node.js**: v18+ (recomendado v20 ou v22)
- **Python**: 3.10+ (para o backend FastAPI)
- **PostgreSQL** (Supabase) configurado conforme o `.env` do backend (`DATABASE_URL` no formato `postgresql+psycopg2://...`)

---

### 2. Executando o Backend (FastAPI)

1. No terminal do backend, crie e ative o ambiente virtual:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\activate

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Crie o arquivo `.env` a partir do `.env.example`:
   ```env
   DATABASE_URL=postgresql+psycopg2://usuario:senha@host:5432/postgres
   SECRET_KEY=sua_chave_secreta_aqui_para_jwt
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=60
   ```

4. Inicie o servidor FastAPI:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   - API disponível em: `http://127.0.0.1:8000`
   - Documentação Swagger: `http://127.0.0.1:8000/docs`

---

### 3. Executando o Frontend (React + Vite)

1. Na pasta do frontend, instale as dependências:
   ```bash
   npm install
   ```

2. *(Opcional)* Crie o arquivo `.env` na raiz do frontend se quiser alterar a URL do backend:
   ```env
   VITE_API_URL=http://127.0.0.1:8000
   ```
   *Nota: Se deixar em branco, o proxy integrado do Vite já redireciona automaticamente `/api` e `/static` para `http://127.0.0.1:8000` sem nenhum problema de CORS!*

3. Inicie o servidor de desenvolvimento:
   ```bash
   npm run dev
   ```
   - Frontend disponível em: `http://localhost:3000`

---

## Acesso

O painel é exclusivo do perfil `admin`. Use as credenciais de administrador fornecidas pela equipe (não há credenciais
padrão neste repositório). Técnicos que entrarem no painel veem apenas uma tela informativa e devem usar o app Android.
A sessão (JWT) fica em `sessionStorage` e é descartada ao fechar a aba ou ao receber 401 da API.

---

## Endpoints consumidos (contrato SDD v0.3, seção 6)

- `POST /api/auth/login`
- `GET|POST /api/tecnicos/` · `PATCH|DELETE /api/tecnicos/{id}` (DELETE = desativação lógica)
- `GET|POST /api/clientes/` · `PATCH|DELETE /api/clientes/{id}` (DELETE = desativação lógica)
- `GET|POST /api/chamados/` (`?is_cancelled=`) · `PATCH /api/chamados/{id}` (atribuição: apenas `id_tecnico_atribuido`)
- `POST /api/chamados/{id}/cancelar` (`{motivo}`) · `POST /api/chamados/{id}/reagendar` (`{data_visita}`)
- `POST /api/chamados/{id}/visitas/{v}/pausar` (`{motivo, descricao?}`) · `GET /api/chamados/{id}/visitas/{v}/estado`
- `GET /api/chamados/{id}/custos`

Não existem no painel: concluir/retomar OS, relatório individual da OS, ajudantes, notificações e dados de fallback.
Em falha da API, as telas exibem o erro e a lista vazia.
