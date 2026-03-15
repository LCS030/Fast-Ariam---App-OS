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

4.  **Execute o servidor:**
    ```bash
    uvicorn app.main:app --reload
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```

## Acesso à API

* **Servidor Local:** `http://127.0.0.1:8000`
* **Documentação Interativa (Swagger):** `http://127.0.0.1:8000/docs`
