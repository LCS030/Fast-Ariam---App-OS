# Backend do Projeto Fast Ariam (UniSENAI)

API desenvolvida em FastAPI para o sistema de gerenciamento de Ordens de Serviço da Fast Ariam.

## Como Rodar o Projeto

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/mjfr/projeto-senai-fast-ariam.git
    cd projeto-senai-fast-ariam
    ```

2.  **Crie e ative um ambiente virtual (opcional, porém recomendável):**
    ```bash
    # Windows
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```
    
4.  **Crie o arquivo ```.env``` na raiz e preencha a partir do exemplo ```.env.example```.**
<br><br>
5.  **Crie o banco de dados a partir do arquivo `fast_db.sql` dentro da pasta `mysql`.**
<br><br>
6.  **Execute o servidor:**
    ```bash
    uvicorn app.main:app --reload
    ```

## OBS.:
No dado momento, o usuário administrador é criado a partir da modificação do código (removendo `_admin_user: dict = Depends(require_admin_role)` do
    endpoint `create_chamado` dentro de `/app/api/endpoints/chamados.py`) ou realizando manualmente o insert no banco de dados.

## Acesso à API

* **Servidor Local:** `http://127.0.0.1:8000`
* **Documentação Interativa (Swagger):** `http://127.0.0.1:8000/docs`
