# Roteiro de teste ponta a ponta — API real (uvicorn + Postgres do Supabase)

> **Nota (11/11/2026):** este roteiro foi escrito para a v0.5. Na v0.6 os arquivos passaram para o bucket privado do Supabase Storage (a API não serve mais `/static`), os dados sensíveis passaram a ser cifrados e as chaves `DATA_ENCRYPTION_KEY`, `INDEX_KEY` e `INTEGRITY_KEY` passaram a ser obrigatórias no `.env` (ver `backend/.env.example` e SDD v0.6/v0.6.1). As seções abaixo que falam de disco local valem só para Storage local (dev/teste).

Base: SDD v0.5 (seções 5, 6.5 a 6.13, 10 e 11/11.1) e PRD v0.5 (seções 6.4 a 6.10 e 12). Este roteiro tem **duas rotas
equivalentes**: o script automatizado `backend/scripts/smoke_api.py` (poucos minutos) e o roteiro manual pelo Swagger
(`/docs`). Depois vêm o painel web (pasta `web/`) e o app Android (pasta `frontend/`).

> **Atenção — isto escreve dados reais.** Dev e produção compartilham o mesmo projeto Supabase (risco aceito pelo PO em
> 07/11/2026). Tudo o que o smoke cria fica **gravado no banco real** e os arquivos ficam no **disco do computador que
> roda a API**. Tudo é marcado com o prefixo `TESTE-SMOKE-` para a limpeza (seção 9). Leia a tabela de riscos (seção 10)
> antes de começar.

Resultado da validação local do script (SQLite **temporário**, nunca o banco real): **378 passos OK e 0 falhas** nos 11
blocos. O Postgres do Supabase **ainda não foi exercitado** por este roteiro: esta será a primeira vez que `FOR UPDATE`,
ENUM, JSONB, TIMESTAMPTZ, índices únicos funcionais (`lower`/`upper`) e os CHECKs do Postgres (`btrim`, regex) entram em
jogo (ver seção 11). Os passos do painel (seção 7) e do app (seção 8) **não foram executados** na validação: foram
escritos a partir do código das telas e dos contratos da API.

---

## 1. Pré-requisitos

| Item | Como conferir / fazer |
|---|---|
| Python 3.14 | `python --version` |
| Ambiente virtual | A pasta `backend/.venv` existe, mas **pode estar vazia** (só o `pip`). Instale as dependências nela (abaixo). |
| Dependências | `httpx` e `Pillow` (usadas pelo smoke) já constam em `requirements.txt`. |
| Arquivo `backend/.env` | Já existe (não versionado). Confira as variáveis da tabela abaixo. **Não** cole valores em chats, commits ou prints. |
| Schema aplicado | Além das migrações antigas, o banco precisa das tabelas da v0.5: `equipamento_modelo`, `os_equipamento` (migração `0007_equipamento_os.sql`) e `sync_arquivo` (`0009_sync_arquivo.sql`), além de `sync_evento`. Confira com a consulta da seção 6 (item 0) **antes** de subir a API: se faltar tabela/coluna, o smoke falha já na criação de modelo ou de OS. |

PowerShell:

```powershell
cd D:\Lucas\_Faculdade\7P\Jornada\Fast-Ariam---App-OS\backend
.\.venv\Scripts\Activate.ps1          # se bloquear: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
```

bash (Git Bash):

```bash
cd /d/Lucas/_Faculdade/7P/Jornada/Fast-Ariam---App-OS/backend
source .venv/Scripts/activate
pip install -r requirements.txt
```

### Variáveis do `backend/.env`

| Variável | O que colocar |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://USUARIO:SENHA@HOST:5432/BANCO` (string de conexão do Supabase, em *Project Settings → Database*). Se a senha tiver `@`, `#`, `/` etc., codifique (`%40`, `%23`, `%2F`). |
| `SECRET_KEY` | Uma chave **nova**, com **32 caracteres ou mais**. Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Trocar a chave invalida os tokens antigos (todo mundo precisa fazer login de novo), o que é esperado. |
| `ENV` | `development` |
| `AUTO_CREATE_TABLES` | `false` (o schema já existe; não deixe a API tentar criar nada) |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` (o painel usa proxy do Vite e nem precisa de CORS, mas mantenha). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` (padrão). O smoke dura menos que isso; para o roteiro manual, se o token expirar, faça login de novo. |
| `UPLOAD_DIR` / `ASSINATURA_DIR` | Opcionais. Pastas dos arquivos enviados (padrão `static/uploads` e `static/assinaturas`). |

> Nunca rode `resetar_banco.py` com este `.env`: ele apaga **todas** as tabelas. Só recusa o host remoto sem
> `--allow-remote`, mas não há motivo para chegar perto dele.

---

## 2. Subir a API apontando para o Supabase

O diretório de trabalho **precisa ser `backend/`** (o `app.main` monta a pasta relativa `static/`).

PowerShell:

```powershell
cd D:\Lucas\_Faculdade\7P\Jornada\Fast-Ariam---App-OS\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --port 8000
```

bash:

```bash
cd /d/Lucas/_Faculdade/7P/Jornada/Fast-Ariam---App-OS/backend
source .venv/Scripts/activate
python -m uvicorn app.main:app --port 8000
```

Sem `--reload` de propósito (um reload no meio de um fluxo atrapalha o teste). Para o app em **aparelho físico** use
`--host 0.0.0.0` (e libere a porta 8000 no firewall do Windows); para o emulador Android o padrão serve.

Conferências rápidas (outro terminal):

```powershell
curl.exe http://127.0.0.1:8000/                 # {"status":"A API da Fast Ariam está no ar!"}
start http://127.0.0.1:8000/docs                # Swagger
```

Erros de partida mais comuns:

| Mensagem | Causa |
|---|---|
| `SECRET_KEY não definida` / `DATABASE_URL ... não definida` | `.env` ausente ou rodando fora de `backend/` |
| `password authentication failed` / timeout | `DATABASE_URL` errada, senha sem codificar, ou projeto Free pausado por inatividade (reative no painel do Supabase) |
| `AUTO_CREATE_TABLES não pode ser habilitada com ENV=production` | `ENV=production` com `AUTO_CREATE_TABLES=true` |
| Erros 500 com `relation ... does not exist` / `column ... does not exist` (p.ex. `os_equipamento`, `sync_arquivo`, `conserto_salvo_em`) | migrações `0007`/`0009` não aplicadas; rode `0000_inventario.sql` e a consulta 0 da seção 6 |

---

## 3. Conta de administrador

Os usuários já existem na tabela `tecnico`. Se você sabe e-mail e senha de um **admin ativo**, use-os e pule esta seção.

Se não souber a senha, escolha **uma** das opções (da mais para a menos recomendada):

**A) Redefinir a senha do admin existente (SQL Editor do Supabase).** Gere o hash fora do banco, sem carregar o `.env`:

```powershell
python -c "import bcrypt; print(bcrypt.hashpw(b'TroqueEstaSenha#2026', bcrypt.gensalt()).decode())"
```

```sql
-- confira quem é o admin
SELECT id_tecnico, nome, email, role, is_active FROM tecnico WHERE role = 'admin';
-- troque a senha (cole o hash gerado; ele começa com $2b$12$)
UPDATE tecnico SET password_hash = '<HASH_GERADO>' WHERE email = 'admin@seu-dominio' AND role = 'admin';
```

**B) Criar outro admin com `seed.py`** (grava no banco do `.env`, por isso confira antes):

```powershell
$env:SEED_ADMIN_EMAIL    = "admin-teste@seu-dominio"
$env:SEED_ADMIN_PASSWORD = "SenhaForte#2026"       # 8 a 72 bytes
python seed.py
```

> **Pegadinha:** o `seed.py` grava o admin com o CNPJ marcador `00.000.000/0000-00`, que é **UNIQUE** em `tecnico`. Se o
> admin já existente foi criado pelo próprio seed, o novo falhará com violação de unicidade (e a mensagem de "banco já
> possui o Administrador" só aparece quando o **e-mail** repete). Confira antes:
> `SELECT id_tecnico, email, cnpj FROM tecnico WHERE cnpj = '00.000.000/0000-00';`. Se já houver, use a opção A.

**C) Criar admin pela API** (precisa de um admin logado): `POST /api/tecnicos/` com `"role": "admin"`, CPF e CNPJ válidos
(use os geradores da seção 5) e senha ≥ 8.

---

## 4. Rodar o smoke automatizado

O script só fala HTTP com a API (não toca no banco). Variáveis: `BASE_URL` (padrão `http://127.0.0.1:8000`),
`ADMIN_EMAIL`, `ADMIN_PASSWORD`; opcionais `SMOKE_SKIP_BIG_UPLOAD=1` (pula o upload de 15 MB) e `SMOKE_TIMEOUT` (segundos).

PowerShell (a senha é pedida sem eco, para não ficar no histórico):

```powershell
cd D:\Lucas\_Faculdade\7P\Jornada\Fast-Ariam---App-OS\backend
$env:BASE_URL       = "http://127.0.0.1:8000"
$env:ADMIN_EMAIL    = "admin@seu-dominio"
$env:ADMIN_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "Senha do admin" -AsSecureString)).Password
python scripts/smoke_api.py
$LASTEXITCODE        # 0 = tudo certo, 1 = alguma falha, 2 = configuração/API/login inválidos
Remove-Item Env:ADMIN_PASSWORD
```

bash:

```bash
cd /d/Lucas/_Faculdade/7P/Jornada/Fast-Ariam---App-OS/backend
read -s -p "Senha do admin: " ADMIN_PASSWORD; echo; export ADMIN_PASSWORD
BASE_URL=http://127.0.0.1:8000 ADMIN_EMAIL=admin@seu-dominio python scripts/smoke_api.py
echo "exit=$?"; unset ADMIN_PASSWORD
```

Para guardar a saída num arquivo (inclui o resumo e o SQL de limpeza): acrescente `*> smoke.txt` (PowerShell 7) ou
`| tee smoke.txt` (bash). Não anexe esse arquivo a chamados públicos sem revisar: ele contém e-mails de teste e ids.

Dica de ensaio **sem tocar no banco real**: suba a API com `DATABASE_URL=sqlite:///<arquivo temporário>`, `ENV=test`,
`AUTO_CREATE_TABLES=true` (ou crie as tabelas antes), `SECRET_KEY` de teste e `UPLOAD_DIR`/`ASSINATURA_DIR` temporários,
crie um admin nesse SQLite e aponte o smoke para essa instância (as variáveis definidas no comando têm precedência sobre o
`.env`). Veja as limitações do SQLite na seção 11.

O que ele cobre (um passo = uma linha ✔/✘; cada cenário roda mesmo que o anterior falhe):

| Bloco | Conteúdo |
|---|---|
| a) Autenticação | login admin, `/auth/me` (sem CPF/CNPJ/telefone/banco), token inválido e ausente → 401, senha errada → 401 |
| b) Cadastros e catálogo | cliente com `codigo` aleatório; cliente sem `codigo` → 422; técnico com CPF/CNPJ válidos gerados (máscara 14/18 caracteres); senha curta e CPF inválido → 422. **Catálogo de modelos**: criar 3 modelos; nome vazio → 422; duplicado ignorando maiúsculas/espaços → 409; renomear para nome existente → 409; técnico em qualquer rota do catálogo → 403; desativar (DELETE = desativação lógica, 204) e OS com modelo inativo → 422; reativar |
| c) Cenário 1 | OS **sem** `equipamentos` / `[]` / modelo inexistente / série vazia / série repetida → 422; OS com 2 equipamentos sem técnico → Pendente; atribuir → Agendado + 1 visita + 1 registro de serviço por equipamento; **técnico não cria equipamento** (`POST .../servicos` → 410; POST/PATCH/DELETE de equipamento → 403; `PATCH` do serviço com `numero_serie_atendido`/`nome_equipamento`/`modelo`/… → 422); ida; **iniciar atendimento sem foto de defeito → 409** (lista os 2), com foto só do 1º → 409 (lista só o 2º), com as duas → 200; foto de conserto antes de iniciar → 409; salvar conserto sem defeito principal → 422; **finalizar sem conserto salvo / sem foto de conserto → 409**; conserto 800x600 → 400, 960x1280 e 1280x960 OK; salvar conserto idempotente; CPF inválido → 422; CPF válido + assinatura → 200 e dados NA VISITA; volta (sem foto de fim → 400); OS Finalizado + `data_conclusao`; custo congelado com R$ 880 de materiais; `/concluir` → 404; PATCH de status → 403 |
| d) Cenário 2 | motivo `Outro` sem descrição → 422; `Almoço` → 422; admin pausa mesmo com o conserto ainda pendente (a pausa dispensa as travas de conserto); reagendar Pausado → 409; finalizar atendimento pausado → 400; volta → Aguardando Reagendamento; data passada → 422; reagendar → 201, nova visita **com serviços sem fotos**, pausa antiga encerrada; segundo reagendamento (ida não iniciada) → 200; **visita nova: iniciar atendimento sem foto → 409, com foto → 200** |
| e) Cenário 3 | cancelar sem motivo → 422; com motivo → 200; de novo → 409; OS Finalizada → 409; GET da cancelada → 404; vincular/remover equipamento de OS cancelada → 409; cancelar OS Pausada encerra a pausa |
| f) Cenário 4 | técnico 2 em OS do técnico 1 (GET, estado, equipamentos, serviços, PATCH de serviço, salvar-conserto, upload-foto, iniciar deslocamento, custos) → 403; serviço/equipamento de OUTRA visita/OS na URL → 404/409; técnico em rotas de admin → 403; cliente alheio → 403; sem token → 401 |
| g) Cenário 5 | desativar técnico com OS Agendada + Em Atendimento + Finalizada: duas viram Pendente sem técnico (equipamentos e fotos preservados), a finalizada fica intacta; token antigo → 401 (inclusive em `/sync/minhas-os`); atribuir admin → 400; reatribuir cria visita nova **sem as fotos do técnico anterior**; reaproveita a visita da OS só Agendada |
| h) Cenário 6 | arquivo texto/vazio/GIF/PDF → 422; PNG OK (deslocamento e foto de serviço); > 15 MB → 413; escritas do técnico em OS Finalizada (upload, PATCH de serviço, salvar-conserto) → 409; `POST .../servicos` → 410; snapshot de custo intacto |
| i) Cenário 7 | admin corrige série e modelo até o início do atendimento (auditado), série duplicada → 409, vincula e remove equipamento sem conteúdo (204), com foto → 409; equipamento novo volta a bloquear o início do atendimento; **atendimento iniciado → vincular/corrigir/remover = 409**; correção de fotos/materiais com a OS não finalizada → 409; remover o último equipamento → 409 |
| j) Cenário 8 | **OS Finalizada**: série/modelo/vínculo/remoção → 409; PATCH de serviço do admin com qualquer campo além de `materiais_utilizados` → 422; admin envia foto (conserto exige 960x1280) e remove excedentes, **nunca a última do tipo** (409); técnico não remove (403) nem altera (409); **correção de materiais recalcula o custo** (`congelado=true`, `valores_utilizados` idênticos, só `custo_total_materiais` e `total_geral` mudam, +R$ 880) |
| k) Cenário 9 — sync offline | `/sync/arquivos`: conserto 800x600 → 400, paisagem OK, **mesmo `client_file_id` → `duplicado` com a mesma url**, tipo inválido → 422, outro técnico/admin → 403, PDF disfarçado → 422; `/sync/eventos`: **fluxo completo de 10 eventos até Finalizado** (horário do aparelho preservado, custo congelado), **reenvio do mesmo lote → 10 `duplicado`**; `FOTO_DEFEITO_AUSENTE` (+ `DEPENDENCIA_REJEITADA`) e correção reenviando com novo id; `CONSERTO_INCOMPLETO`; tipo desconhecido → `VALIDACAO`; `ocorrido_em` sem fuso → 422; `ARQUIVO_AUSENTE` (transitório: reenvia os mesmos ids depois do arquivo); `OS_CANCELADA` e `OS_REATRIBUIDA`; `/sync/minhas-os` (só OS do técnico, com equipamentos, serviços e estado da visita vigente) |

No fim ele imprime: resumo por cenário, lista de falhas, **IDs criados** (clientes, técnicos, modelos, OS) e um **SQL de
limpeza sugerido** (já com `equipamento_modelo`, `os_equipamento`, `sync_evento` e `sync_arquivo`). O script **não apaga nada**.

---

## 5. Roteiro manual pelo Swagger (`http://127.0.0.1:8000/docs`)

Equivale ao smoke, na ordem. Convenções: `{os}`, `{v}` (visita), `{s1}`, `{s2}` (serviços, um por equipamento), `{c}`
(cliente), `{m}` (modelo), `{eq1}`, `{eq2}` (`id_os_equipamento`), `{t1}`, `{t2}` (técnicos) são os ids devolvidos nas
respostas. Prefixe nomes/descrições com **`TESTE-SMOKE-`**.

**Preparação.** *Authorize* (cadeado) → `username` = e-mail do admin, `password` = senha; deixe `client_id`/`client_secret`
vazios. Para trocar de usuário: *Authorize → Logout* e entre de novo. Arquivos e valores úteis (rode uma vez em `backend/`):

```powershell
# imagens: defeito (pequena), conserto OK (960x1280) e conserto pequena (800x600)
python -c "from PIL import Image; Image.new('RGB',(200,150),'blue').save('defeito.jpg'); Image.new('RGB',(960,1280),'red').save('conserto_ok.jpg'); Image.new('RGB',(800,600),'red').save('conserto_pequena.jpg'); Image.new('RGB',(200,80),'white').save('assinatura.png'); open('nao_e_imagem.jpg','w').write('texto')"
# assinatura em base64 (copie a linha impressa para o campo assinatura_base64)
python -c "import base64,io;from PIL import Image;b=io.BytesIO();Image.new('RGB',(200,80),'white').save(b,'PNG');print('data:image/png;base64,'+base64.b64encode(b.getvalue()).decode())"
# CPF e CNPJ válidos para os técnicos
python -c "import sys; sys.path.insert(0,'scripts'); import smoke_api as s; print(s.gerar_cpf(), s.gerar_cnpj())"
# UUIDs para o bloco de sincronização (um por arquivo e um por evento)
python -c "import uuid; print(*[uuid.uuid4() for _ in range(12)], sep='\n')"
```

CPF válido do **cliente** na assinatura: `529.982.247-25`. CPF inválido: `111.111.111-11`. Apague os arquivos de teste depois.

### 5.1 Cadastros e catálogo de modelos

| # | Chamada | Corpo / campos | Esperado |
|---|---|---|---|
| 1 | `POST /api/auth/login` | (via Authorize) | 200 com `access_token` |
| 2 | `GET /api/auth/me` | — | 200, `role=admin`, sem cpf/cnpj/telefone/banco. Teste também sem Authorize → 401 |
| 3 | `POST /api/clientes/` | `{"razao_social":"TESTE-SMOKE-CLIENTE","telefone":"2733334444","endereco":"RUA DOS TESTES","numero":"100","bairro":"CENTRO","cidade":"SERRA","uf":"ES","codigo":1700000001}` | 201 → guarde `{c}`. Repetir o mesmo `codigo` → 409. Sem `codigo` → 422 |
| 4 | `POST /api/tecnicos/` | `{"nome":"TESTE-SMOKE-tec1","cnpj":"<gerado>","cpf":"<gerado>","inscricao_estadual":"ISENTO","email":"teste-smoke-tec1@exemplo.com.br","telefone":"(27) 99999-0000","password":"Senha#Teste123","role":"tecnico","is_active":true,"dados_bancarios":{"banco":"Banco Teste","agencia":"0001","conta":"12345-6","pix":"teste-smoke-tec1@exemplo.com.br"}}` | 201, `cpf` com 14 e `cnpj` com 18 caracteres (mascarados), sem senha na resposta → `{t1}`. Repetir → 409. `password` com 5 caracteres → 422. CPF `111.111.111-11` → 422 |
| 5 | Repita o 4 para um segundo técnico (`tec2`, e-mail/CNPJ/CPF diferentes) | | 201 → `{t2}` |
| 6 | `POST /api/equipamentos/` (admin) | `{"modelo":"TESTE-SMOKE-MODELO-A"}` | 201, `is_active=true` → `{m}`. Repetir com `"teste-smoke-modelo-a"` ou `"  TESTE-SMOKE-MODELO-A  "` → **409**. `{"modelo":"   "}` ou `{}` → 422. Crie também `TESTE-SMOKE-MODELO-B` |
| 7 | `GET /api/equipamentos/`, `GET /api/equipamentos/{m}` (admin) | — | 200; id inexistente → 404 |
| 8 | `PATCH /api/equipamentos/{B}` | `{"modelo":"teste-smoke-modelo-a"}` depois `{"modelo":"TESTE-SMOKE-MODELO-B2"}` | 409 e depois 200 (renomear reescreve o nome exibido no histórico) |
| 9 | Como **t1** (Authorize): `POST/GET/PATCH/DELETE /api/equipamentos/...` | qualquer | **403** em todas (o técnico só recebe os equipamentos embutidos na OS) |
| 10 | Como admin: `DELETE /api/equipamentos/{C}` (um modelo C extra) | — | **204** = desativação lógica; `GET` mostra `is_active=false`. `POST /api/chamados/` com esse modelo → 422. `PATCH {"is_active":true}` reativa |

### 5.2 Cenário 1 — fluxo normal (2 equipamentos)

| # | Chamada (usuário) | Corpo | Esperado |
|---|---|---|---|
| 1 | `POST /api/chamados/` (admin) | sem `equipamentos`; depois com `"equipamentos":[]`; com `{"id_equipamento_modelo":99999999,"numero_serie":"X"}`; com série `"   "`; com a mesma série repetida (`ab-1` e `AB-1`) | **422** em todas |
| 2 | `POST /api/chamados/` (admin) | `{"id_cliente":{c},"descricao_cliente":"TESTE-SMOKE-1 gondola sem refrigeracao","pedido":"PED-SMOKE-1","em_garantia":true,"equipamentos":[{"id_equipamento_modelo":{m},"numero_serie":"SMK-0001"},{"id_equipamento_modelo":{m},"numero_serie":"SMK-0002"}]}` | 201, `status=Pendente`, `id_tecnico_atribuido=null`, `visitas=[]`, **2 itens em `equipamentos`** → `{os}`, `{eq1}`, `{eq2}` |
| 3 | `PATCH /api/chamados/{os}` (admin) | `{"id_tecnico_atribuido":{t1}}` | 200, `status=Agendado`, **1 visita** em `visitas` → `{v}`. Enviar `status` livre → 409/403 |
| 4 | `POST /api/chamados/{os}/visitas` (admin) | `{"data_visita":"<hoje>"}` | **409** (já existe visita aberta) |
| 5 | Authorize como **tec1**; `GET /api/chamados/` | — | 200; só OS do tec1 |
| 6 | `GET .../visitas/{v}/servicos` | — | **2 registros** (um por equipamento) → `{s1}`, `{s2}`; `numero_serie`/`modelo` preenchidos, `conserto_salvo_em=null`, `is_legado=false` |
| 7 | `POST .../visitas/{v}/servicos` (tec1) | `{"numero_serie_atendido":"SN","nome_equipamento":"X"}` | **410** (o técnico não cria equipamento nem serviço) |
| 8 | `POST /api/chamados/{os}/equipamentos`, `PATCH`/`DELETE .../equipamentos/{eq1}` (tec1) | `{"id_equipamento_modelo":{m},"numero_serie":"HACK"}` / `{"numero_serie":"HACK"}` | **403**. `GET /api/chamados/{os}/equipamentos` → 200 com só `id_os_equipamento`, `id_equipamento_modelo`, `modelo`, `numero_serie` |
| 9 | `PATCH .../servicos/{s1}` (tec1) | `{"numero_serie_atendido":"HACK"}`, depois `{"nome_equipamento":"X"}`, `{"modelo":"X"}`, `{"id_os_equipamento":999}` | **422** em todos (campo fora do contrato; nada muda) |
| 10 | `GET .../visitas/{v}/estado` | — | `pode_iniciar_deslocamento_ida=true`, demais `false` |
| 11 | `POST .../visitas/{v}/iniciar-deslocamento` | `{"tipo":"ida","km_inicio":1000}` | 200. Repetir → 400 |
| 12 | `POST .../visitas/{v}/upload-deslocamento` | `file`=`defeito.jpg`, `tipo`=`ida`, `momento`=`inicio` | 200, `foto_inicio_ida_url` preenchida |
| 13 | `POST .../visitas/{v}/finalizar-deslocamento` | `{"tipo":"ida","km_fim":900}` depois `{"tipo":"ida","km_fim":1020}` | 400 (km menor) e depois 200 |
| 14 | `POST .../visitas/{v}/iniciar-atendimento` | (vazio) | **409** "…sem foto do defeito de cada equipamento. Pendentes: …" listando **os dois**. Em `.../estado`: `pode_iniciar_atendimento=false`, `bloqueio_iniciar_atendimento` com o mesmo texto, `equipamentos[].foto_defeito=false` |
| 15 | `POST .../servicos/{s1}/upload-foto` | `tipo=conserto`, `file=conserto_ok.jpg` | **409** (foto de conserto só depois de iniciar o atendimento). `POST .../servicos/{s1}/salvar-conserto` `{}` → **400** |
| 16 | `POST .../servicos/{s1}/upload-foto` | `tipo=defeito`, `file=defeito.jpg` | 200 (foto de defeito pequena é aceita). Repita o 14: **409 listando só o equipamento 2** |
| 17 | `POST .../servicos/{s2}/upload-foto` | `tipo=defeito`, `file=defeito.jpg`; depois repita o 14 | 200; `iniciar-atendimento` → **200**; `GET /api/chamados/{os}` → `Em Atendimento` |
| 18 | `PATCH .../servicos/{s1}` | `{"defeitos_principais":["Inventado"]}` | 422 |
| 19 | `POST .../servicos/{s1}/salvar-conserto` | `{}` | **422** ("defeito principal") enquanto `defeitos_principais` estiver vazio |
| 20 | `POST .../visitas/{v}/finalizar-atendimento` | corpo válido (item 27) | **409** ("…conserto…" dos dois equipamentos). Nada é gravado |
| 21 | `PATCH .../servicos/{s1}` | `{"defeitos_principais":["Refrigeração"],"sub_defeitos_refrigeracao":["Compressor"],"sub_defeitos_compressor":["Queimado"],"materiais_utilizados":[{"nome":"Compressor 1/4 HP","quantidade":1,"valor":850.00}]}` | 200; **nenhum campo de série/modelo é alterado** |
| 22 | `POST .../servicos/{s1}/salvar-conserto` | `{}` (duas vezes) | 200 com `conserto_salvo_em`; a 2ª devolve a **mesma** marca (idempotente). `PATCH {"defeitos_principais":[]}` depois de salvar → 422 |
| 23 | `POST .../servicos/{s1}/upload-foto` | `tipo=conserto`, `conserto_ok.jpg` (960x1280); depois uma 1280x960; depois `conserto_pequena.jpg` | 200, 200 e **400** "Resolução insuficiente" |
| 24 | `GET .../servicos/{s1}/fotos` | — | 1 em `fotos_defeito` e 2 em `fotos_conserto` |
| 25 | `POST .../visitas/{v}/finalizar-atendimento` (corpo do item 27) | | **409** citando só o equipamento 2 (conserto não salvo). Envie `conserto_ok.jpg` para `{s2}` (foto de conserto **antes** de salvar vale, mas não basta): ainda 409. Depois `PATCH .../servicos/{s2}` com `{"defeitos_principais":["Refrigeração"],"materiais_utilizados":[{"nome":"Filtro secador","quantidade":2,"valor":15}]}` e `salvar-conserto` `{}` |
| 26 | `GET .../visitas/{v}/estado` | — | `pode_finalizar_atendimento=true` só quando os dois equipamentos tiverem conserto salvo **e** foto de conserto; antes disso, `bloqueio_finalizar_atendimento` traz o texto do 409 |
| 27 | `POST .../visitas/{v}/finalizar-atendimento` | `{"nome_cliente":"Maria Souza","documento_cliente":"111.111.111-11","assinatura_base64":"<b64>"}` | **422** (CPF inválido). Com `"529.982.247-25"` → 200 `{"status":"ok","assinatura_url":...}`; `documento_cliente` da visita = `52998224725` |
| 28 | `POST .../visitas/{v}/iniciar-deslocamento` | `{"tipo":"volta","km_inicio":1020}` | 200 |
| 29 | `POST .../visitas/{v}/finalizar-deslocamento` | `{"tipo":"volta","km_fim":1040}` | **400** (falta a foto de fim) |
| 30 | `upload-deslocamento` | `tipo=volta`, `momento=fim`, `defeito.jpg` e, em seguida, repita o 29 | 200; depois 200 com `servico_finalizado=true`, `km_total=40` |
| 31 | `GET /api/chamados/{os}` | — | `status=Finalizado`, `data_conclusao` preenchida |
| 32 | `GET /api/chamados/{os}/custos` | — | `congelado=true`, `custo_total_materiais=880` (850 + 2 x 15), `total_geral>0`, `valores_utilizados` |
| 33 | `POST /api/chamados/{os}/concluir` | — | **404/405** |
| 34 | `PATCH /api/chamados/{os}` com `{"status":"Finalizado"}` como tec1 e como admin | | **403** nos dois |

### 5.3 Cenário 2 — pausa, reagendamento e novas exigências de foto

Crie nova OS (1 equipamento), atribua ao tec1, faça ida completa, **foto de defeito** e `iniciar-atendimento` (passos 2, 3, 11–14 e 16–17 acima).

| # | Chamada | Corpo | Esperado |
|---|---|---|---|
| 1 | `POST .../visitas/{v}/pausar` (admin) | `{"motivo":"Outro"}` | 422 |
| 2 | idem | `{"motivo":"Almoço"}` | 422 |
| 3 | idem | `{"motivo":"Outro","descricao":"Cliente pediu para aguardar"}` | 200, `por_papel=admin`, `is_ativa=true`; OS `Pausado`. **Funciona mesmo sem conserto salvo nem foto de conserto** (a pausa dispensa essas exigências) |
| 4 | `POST /api/chamados/{os}/reagendar` (admin) | `{"data_visita":"<hoje+3>"}` | **409** (Pausado) |
| 5 | `POST .../visitas/{v}/finalizar-atendimento` (tec1) | corpo válido | **400** (OS pausada; a checagem de pausa vem antes das travas) |
| 6 | `POST .../servicos/{s}/salvar-conserto` (tec1) | `{}` | **400** (OS pausada) |
| 7 | (tec1) iniciar volta, foto de fim da volta, finalizar volta | como 5.2 passos 28–30 | OS `Aguardando Reagendamento` (e **não** Finalizado); custo **não** congelado |
| 8 | `POST /api/chamados/{os}/reagendar` (admin) | `{"data_visita":"<ontem>"}` | **422** |
| 9 | idem | `{"data_visita":"<hoje+3>"}` | **201**; OS `Agendado`, `data_agendamento` nova, **2 visitas**; pausa antiga com `is_ativa=false` e `encerrada_em` |
| 10 | `GET .../visitas/{nova}/servicos` e `.../visitas/{v}/estado` | — | a visita nova tem **1 serviço por equipamento, sem fotos**; o `estado` da visita antiga tem `visita_vigente=false`, `equipamentos=[]` |
| 11 | idem 9, nova data | `{"data_visita":"<hoje+5>"}` | **200** (ida não iniciada: muda a data da visita, sem criar outra) |
| 12 | (tec1) ida completa na visita nova e `iniciar-atendimento` | | **409** (as fotos da visita 1 não valem para a visita 2); depois da foto de defeito → 200 |

### 5.4 Cenário 3 — cancelamento

| # | Chamada (admin) | Corpo | Esperado |
|---|---|---|---|
| 1 | nova OS; `POST /api/chamados/{os}/cancelar` | `{}` | 422 |
| 2 | idem | `{"motivo":"Cliente desmarcou"}` | 200; `is_cancelled=true`, `cancelado_em`, `cancelado_por` |
| 3 | idem de novo | `{"motivo":"outra vez"}` | 409 |
| 4 | `GET /api/chamados/{os}` | — | **404** |
| 5 | `GET /api/chamados/?is_cancelled=true` | — | a OS aparece |
| 6 | `POST /api/chamados/{os}/equipamentos` e `DELETE .../equipamentos/{eq}` na OS cancelada | | **409** |
| 7 | `POST /api/chamados/{os da seção 5.2}/cancelar` | `{"motivo":"x"}` | **409** (Finalizado) |

### 5.5 Cenário 4 — permissões

Com **tec2** autenticado, na OS do tec1 (Agendada): `GET /api/chamados/{os}`, `GET .../estado`, `GET .../equipamentos`,
`GET .../servicos`, `PATCH .../servicos/{s}`, `POST .../servicos/{s}/salvar-conserto`, `POST .../servicos/{s}/upload-foto`,
`POST .../iniciar-deslocamento` → **403** em todos. Com **tec1**: `POST /api/chamados/` → 403; `GET /api/tecnicos/` → 403;
`GET /api/clientes/` → 403; `GET /api/clientes/{id de um cliente sem OS dele}` → **403**; `GET /api/clientes/{c}` (cliente da
OS dele) → 200; `PATCH .../servicos/{s de OUTRA OS}` → **404**. Sem Authorize: qualquer rota → 401.

### 5.6 Cenário 5 — desativação (RN-08a)

Use um técnico **só de teste** (`tec3`). Crie 3 OS dele: A (só atribuída), B (ida + foto de defeito + `iniciar-atendimento`),
C (fluxo completo → Finalizado). Depois, como admin: `DELETE /api/tecnicos/{tec3}` → **204**. Esperado: A e B em `Pendente`
sem técnico (**equipamentos e fotos preservados**); C `Finalizado` com o mesmo técnico e o mesmo custo; com o token antigo do
tec3 `GET /api/auth/me` e `GET /api/sync/minhas-os` → **401**; login do tec3 → 401. `PATCH /api/chamados/{A}` com
`{"id_tecnico_atribuido":<id do admin>}` → **400**. Reatribua B ao `tec4`: `Agendado`, **2 visitas** (a antiga fica como
histórico; `ida_inicio_em` dela preservado); a visita nova tem 1 serviço por equipamento **sem fotos**; o tec4 inicia a ida na
visita nova; na visita antiga `iniciar-deslocamento` → 409. Reatribua A ao `tec4`: continua **1 visita** (reaproveitada).

### 5.7 Cenário 6 — uploads

Com uma OS em ida iniciada e `upload-deslocamento`: `nao_e_imagem.jpg` → **422**; arquivo vazio → 422; GIF/PDF renomeado → 422;
PNG real → 200. A mesma bateria vale para `.../servicos/{s}/upload-foto` (texto disfarçado de JPEG → 422; PNG → 200).
Imagem > 15 MB: crie `python -c "open('grande.jpg','wb').write(b'\xff\xd8\xff\xe0'+bytes(16*1024*1024))"` → **413**.
Como **tec1**, na OS **Finalizada** da seção 5.2: `upload-deslocamento`, `upload_file` e `.../servicos/{s}/upload-foto` → **409**;
`PATCH .../servicos/{s}` e `salvar-conserto` → 409/400; `POST .../servicos` → 410.

### 5.8 Cenário 7 — equipamentos da OS: edição do admin

Crie uma OS atribuída ao tec1 com 2 equipamentos (`E1`, `E2`) e use o `id_os_equipamento` de cada um.

| # | Chamada (admin) | Corpo | Esperado |
|---|---|---|---|
| 1 | `PATCH /api/chamados/{os}/equipamentos/{E1}` | `{"numero_serie":"SMK-E1B","id_equipamento_modelo":{B}}` | 200 (auditado: `OS_EQUIPAMENTO_ALTERADO`); `GET .../servicos` mostra a série corrigida |
| 2 | idem | `{"numero_serie":"<série do E2 em minúsculas>"}` | **409** (duplicada na OS, ignora maiúsculas) |
| 3 | `POST /api/chamados/{os}/equipamentos` | `{"id_equipamento_modelo":{m},"numero_serie":"SMK-E3"}` | **201** e a visita aberta ganha o 3º registro de serviço; `DELETE .../equipamentos/{E3}` → **204** (sem conteúdo) |
| 4 | (tec1) ida completa e foto de defeito dos equipamentos; admin: `DELETE .../equipamentos/{E2}` | | **409** (já tem foto) |
| 5 | admin: `POST .../equipamentos` (novo equipamento) | | 201; `GET .../estado` → `pode_iniciar_atendimento=false`; `iniciar-atendimento` → 409 até a foto do novo (ou remova-o: 204) |
| 6 | (tec1) `iniciar-atendimento` | | 200 |
| 7 | admin: `POST`/`PATCH`/`DELETE` em `.../equipamentos` | | **409** em todos (do início do atendimento até a finalização não se edita) |
| 8 | admin: `PATCH .../servicos/{s}` `{"materiais_utilizados":[]}`, `POST .../servicos/{s}/upload-foto`, `DELETE .../fotos/1` | | **409** (a correção só vale com a OS Finalizada) |
| 9 | OS com 1 equipamento: `DELETE .../equipamentos/{E}` | | **409** ("último equipamento") |

### 5.9 Cenário 8 — OS Finalizada: correção de fotos e materiais

Use a OS finalizada da seção 5.2 (`{os}`, `{v}`, `{s1}`). Sempre como **admin**, salvo indicação.

| # | Chamada | Corpo | Esperado |
|---|---|---|---|
| 1 | `PATCH .../equipamentos/{eq1}`, `POST .../equipamentos`, `DELETE .../equipamentos/{eq1}` | `{"numero_serie":"OUTRA"}` / `{"id_equipamento_modelo":{B}}` | **409** (modelo e série ficam travados) |
| 2 | `PATCH .../servicos/{s1}` | `{"defeitos_principais":["Refrigeração"]}`; `{}`; `{"materiais_utilizados":[],"defeitos_principais":["Refrigeração"]}` | **422** (só `materiais_utilizados`) |
| 3 | `POST .../servicos/{s1}/upload-foto` | `tipo=conserto`, `conserto_ok.jpg`; depois `defeito.jpg` como `conserto` | 200 e **400** (960x1280 também na correção); `tipo=defeito` pequena → 200 |
| 4 | `DELETE .../servicos/{s1}/fotos/{id_foto}` | foto antiga de conserto; depois a **última** de conserto | 204 e **409** ("única foto"). Idem para defeito: excedentes 204, a última 409. `fotos/99999999` → 404 |
| 5 | (tec1) `DELETE .../fotos/{id}` | | **403**. (tec1) `PATCH .../servicos/{s1}` → 409 |
| 6 | `GET /api/chamados/{os}/custos` | — | **anote** `total_geral`, `custo_total_materiais` e `valores_utilizados` (fotos não alteram o custo) |
| 7 | `PATCH .../servicos/{s1}` | `{"materiais_utilizados":[{"nome":"Compressor 1/4 HP","quantidade":2,"valor":850},{"nome":"Filtro","quantidade":3,"valor":10}]}` | 200 |
| 8 | `GET /api/chamados/{os}/custos` | — | `congelado=true`; `valores_utilizados` **idênticos** ao item 6 (a configuração global atual não entra); `custo_total_materiais` e `total_geral` sobem **R$ 880,00** (1.730 − 850); km, deslocamento, serviço, pedágio e frete iguais; OS continua `Finalizado` |

### 5.10 Cenário 9 — sincronização offline (`/api/sync`)

Só o técnico sincroniza (admin → 403). Gere UUIDs (seção 5, preparação). Crie uma OS (1 equipamento) atribuída ao tec1 e anote
`{os}`, `{v}` e `{s}`. No Swagger, `POST /api/sync/arquivos` é `multipart/form-data` (campos `client_file_id`, `tipo_arquivo`,
`id_os`, `id_visita`, `file`) e `POST /api/sync/eventos` é JSON. Todos os horários precisam de **fuso** (`...-03:00` ou `Z`).

| # | Chamada (tec1) | Corpo | Esperado |
|---|---|---|---|
| 1 | `POST /api/sync/arquivos` | `tipo_arquivo=foto_conserto`, `conserto_pequena.jpg` | **400** |
| 2 | idem | `tipo_arquivo=foto_conserto`, `conserto_ok.jpg`, `client_file_id=<U1>` | 200 `{"resultado":"aplicado","url":...}` |
| 3 | **repita o 2** com o **mesmo** `client_file_id` | | 200 `{"resultado":"duplicado"}` e a **mesma** `url` (idempotência) |
| 4 | idem | `tipo_arquivo=outro` → 422; admin → 403; tec2 → 403; PDF renomeado → 422 | |
| 5 | Envie os arquivos do fluxo: `foto_deslocamento` (ida, `<UA>`), `foto_defeito` (`<UB>`), `foto_conserto` 960x1280 (`<UC>`), `assinatura` (`assinatura.png`, `<UD>`), `foto_deslocamento` (volta, `<UE>`) | | 200 cada |
| 6 | `POST /api/sync/eventos` | `{"dispositivo_id":"swagger","enviado_em":"<agora com fuso>","eventos":[ ... 10 eventos ... ]}` (modelo abaixo) | 200; **10 × `aplicado`**; `GET /api/chamados/{os}` → `Finalizado`; `ida_inicio_em` = o `ocorrido_em` informado (horário do aparelho, não o do recebimento); custo congelado |
| 7 | **repita o 6** sem alterar nada | | 200; **10 × `duplicado`**; nenhuma foto duplicada |
| 8 | OS nova: envie só `atendimento_iniciado` (com ida finalizada) sem foto de defeito | | `rejeitado` / `FOTO_DEFEITO_AUSENTE`; o evento seguinte da visita → `DEPENDENCIA_REJEITADA`; OS segue `Agendado`. Envie a foto e reenvie a ação com **novo** `client_event_id` → `aplicado` |
| 9 | OS em atendimento: `atendimento_finalizado` sem conserto salvo/foto | | `rejeitado` / `CONSERTO_INCOMPLETO` |
| 10 | evento com `foto_ref` de um `client_file_id` que **ainda não foi enviado** | | `rejeitado` / `ARQUIVO_AUSENTE` (nada é gravado); envie o arquivo e reenvie os **mesmos** `client_event_id` → `aplicado` |
| 11 | evento com `tipo` desconhecido, `km_inicio` ausente ou CPF inválido → `rejeitado` / `VALIDACAO`; `ocorrido_em` sem fuso → **422** do lote inteiro | | |
| 12 | Cancele a OS (admin) e envie um evento dela → `OS_CANCELADA`; reatribua a OS a outro técnico e envie → `OS_REATRIBUIDA` | | |
| 13 | `GET /api/sync/minhas-os` (tec1) e `?desde=2026-01-01T00:00:00Z` | — | 200; `sincronizado_em`, `os[].chamado` (com `equipamentos`, `visitas[].servicos_realizados`) e `os[].estado_visita_vigente`; **nunca** OS de outro técnico nem canceladas |

Modelo dos 10 eventos do item 6 (cada `client_event_id` é um UUID novo; `id_os`, `id_visita` e `ocorrido_em` em todos;
`ocorrido_em` crescente, p.ex. de 3 h atrás até 2 h atrás):

```text
deslocamento_ida_iniciado        {"km_inicio":1000,"foto_ref":"<UA>"}
deslocamento_ida_finalizado      {"km_fim":1020}
foto_servico                     {"id_servico":{s},"tipo":"defeito","foto_ref":"<UB>"}
atendimento_iniciado             {}
servico_salvo                    {"id_servico":{s},"defeitos_principais":["Refrigeração"],"materiais_utilizados":[{"nome":"Compressor 1/4 HP","quantidade":1,"valor":850}]}
foto_servico                     {"id_servico":{s},"tipo":"conserto","foto_ref":"<UC>"}
conserto_salvo                   {"id_servico":{s}}
atendimento_finalizado           {"nome_cliente":"Maria Souza","documento_cliente":"529.982.247-25","assinatura_ref":"<UD>"}
deslocamento_volta_iniciado      {"km_inicio":1020}
deslocamento_volta_finalizado    {"km_fim":1040,"foto_ref":"<UE>"}
```

---

## 6. Checklist de verificação no banco (somente SELECT — SQL Editor do Supabase)

Troque `:os` pelo id da OS do cenário 1 (`:os2` pelo do cenário 2 e `:os9` pela OS finalizada por sincronização).

```sql
-- 0) Schema da v0.5 presente? (rode ANTES de subir a API; deve devolver as 4 tabelas e as colunas novas)
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND table_name IN ('equipamento_modelo','os_equipamento','sync_evento','sync_arquivo');
SELECT column_name FROM information_schema.columns
WHERE table_name = 'servico_equipamento' AND column_name IN ('id_os_equipamento','conserto_salvo_em','is_legado');

-- 1) OS finalizada: status, conclusão e atribuição
SELECT id_os, status, data_abertura, data_agendamento, data_conclusao, id_tecnico_atribuido, is_cancelled
FROM ordem_servico WHERE id_os = :os;                                   -- Finalizado, data_conclusao = hoje

-- 2) Custo congelado (1 linha por OS) e valores globais usados
SELECT id_os, total, calculado_em, detalhes->>'total_geral' AS total_json,
       detalhes->>'custo_total_materiais' AS materiais, valores_utilizados
FROM custo_os WHERE id_os = :os;                                         -- total > 0; materiais = 880 (1.760 após a correção do cenário 8: ver nota)

-- 3) Visita: marcos, km, assinatura e CPF (11 dígitos) NA VISITA
SELECT id_visita, data_visita, servico_finalizado, km_inicio_ida, km_fim_ida, km_inicio_volta, km_fim_volta, km_total,
       ida_inicio_em, ida_fim_em, atendimento_inicio_em, atendimento_fim_em, volta_inicio_em, volta_fim_em,
       assinatura_url, nome_cliente_assinatura, documento_cliente,
       foto_inicio_ida_url IS NOT NULL AS foto_ida, foto_fim_volta_url IS NOT NULL AS foto_volta
FROM visita WHERE id_os = :os;                                           -- 1 visita finalizada; documento_cliente = 52998224725

-- 4) Equipamentos da OS (modelo do catálogo + série) e 1 serviço por equipamento por visita
SELECT oe.id_os_equipamento, oe.id_os, m.modelo, m.is_active, oe.numero_serie, oe.origem
FROM os_equipamento oe JOIN equipamento_modelo m USING (id_equipamento_modelo)
WHERE oe.id_os = :os ORDER BY oe.id_os_equipamento;                      -- 2 linhas, origem = 'admin'
SELECT s.id_servico, s.id_visita, s.id_os_equipamento, s.is_legado, s.conserto_salvo_em, s.numero_serie_atendido
FROM servico_equipamento s WHERE s.id_visita IN (SELECT id_visita FROM visita WHERE id_os = :os);
                                                                         -- 2 linhas, is_legado = false, conserto_salvo_em preenchido, numero_serie_atendido NULL

-- 5) Materiais e fotos por serviço
SELECT s.id_servico, m.nome, m.quantidade, m.valor
FROM servico_equipamento s LEFT JOIN material m ON m.id_servico = s.id_servico
WHERE s.id_visita IN (SELECT id_visita FROM visita WHERE id_os = :os);
SELECT f.id_servico, f.tipo, count(*) FROM servico_foto f
WHERE f.id_servico IN (SELECT id_servico FROM servico_equipamento WHERE id_visita IN (SELECT id_visita FROM visita WHERE id_os = :os))
GROUP BY f.id_servico, f.tipo;     -- cada serviço: defeito >= 1 e conserto >= 1 (800x600 não grava). Após o cenário 8: exatamente 1 de cada no serviço corrigido

-- 6) Auditoria da OS: deve contar a história inteira
SELECT criado_em, papel, acao, id_usuario, payload FROM log_acao WHERE id_os = :os ORDER BY id;
-- esperado (ordem): OS_CRIADA, OS_ATRIBUIDA, UPLOAD_ARQUIVO..., ATENDIMENTO_INICIADO (payload.equipamentos_conferidos),
--   SERVICO_ATUALIZADO, CONSERTO_SALVO (1 por equipamento), ATENDIMENTO_FINALIZADO (payload.equipamentos_conferidos), OS_FINALIZADA,
--   e, se o cenário 8 rodou: FOTO_CORRIGIDA_ADMIN (acao enviada/removida, tipo) e MATERIAIS_CORRIGIDOS_ADMIN (materiais_antes/depois, custo_total_anterior/novo)
-- ATENÇÃO: payload não deve conter CPF completo, senha, token nem dados bancários.
SELECT criado_em, acao, payload FROM log_acao
WHERE acao IN ('EQUIPAMENTO_MODELO_CRIADO','EQUIPAMENTO_MODELO_ATUALIZADO','EQUIPAMENTO_MODELO_DESATIVADO')
  AND CAST(payload AS TEXT) LIKE '%TESTE-SMOKE-%' ORDER BY id;           -- ações do catálogo (id_os NULL)
SELECT criado_em, acao, payload FROM log_acao
WHERE id_os = :os AND acao IN ('OS_EQUIPAMENTO_VINCULADO','OS_EQUIPAMENTO_ALTERADO','OS_EQUIPAMENTO_REMOVIDO') ORDER BY id;

-- 7) Pausa encerrada após o reagendamento (cenário 2)
SELECT p.id_pausa, p.visita_id, p.motivo, p.descricao, p.por_papel, p.por_usuario_id, p.is_ativa, p.criado_em, p.encerrada_em
FROM pausa p WHERE p.visita_id IN (SELECT id_visita FROM visita WHERE id_os = :os2);   -- is_ativa=false, encerrada_em preenchida, por_papel=admin
SELECT id_os, status, data_agendamento, (SELECT count(*) FROM visita v WHERE v.id_os = o.id_os) AS visitas
FROM ordem_servico o WHERE id_os = :os2;                                  -- Agendado (ou Em Atendimento), 2 visitas
SELECT v.id_visita, count(s.id_servico) AS servicos,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM servico_foto f WHERE f.id_servico = s.id_servico AND f.tipo = 'defeito')) AS com_foto_defeito
FROM visita v LEFT JOIN servico_equipamento s ON s.id_visita = v.id_visita
WHERE v.id_os = :os2 GROUP BY v.id_visita ORDER BY v.id_visita;          -- cada visita tem 1 serviço por equipamento; as fotos de defeito são POR VISITA
SELECT acao, payload FROM log_acao WHERE id_os = :os2 AND acao IN ('OS_PAUSADA','OS_AGUARDANDO_REAGENDAMENTO','OS_REAGENDADA') ORDER BY id;

-- 8) Sincronização offline (cenário 9)
SELECT tipo, ocorrido_em, recebido_em, resultado, codigo, detalhe
FROM sync_evento WHERE id_os = :os9 ORDER BY ocorrido_em;                -- 10 'aplicado'; ocorrido_em (aparelho) ANTES de recebido_em
SELECT client_event_id, count(*) FROM sync_evento GROUP BY client_event_id HAVING count(*) > 1;      -- ZERO linhas (sem duplicidade)
SELECT resultado, codigo, count(*) FROM sync_evento
WHERE id_tecnico IN (SELECT id_tecnico FROM tecnico WHERE nome LIKE 'TESTE-SMOKE-%') GROUP BY resultado, codigo ORDER BY 1, 2;
                                                                         -- aplicado; rejeitado: FOTO_DEFEITO_AUSENTE, DEPENDENCIA_REJEITADA, CONSERTO_INCOMPLETO, VALIDACAO, OS_CANCELADA, OS_REATRIBUIDA
                                                                         -- (ARQUIVO_AUSENTE NÃO aparece: é transitório e não é gravado)
SELECT tipo_arquivo, count(*) FROM sync_arquivo WHERE id_os = :os9 GROUP BY tipo_arquivo;   -- 5 arquivos do fluxo (1 por client_file_id)
SELECT acao, papel, payload FROM log_acao WHERE acao = 'CONFLITO_ADMINISTRATIVO' ORDER BY id DESC LIMIT 5;  -- ator 'sistema' (só aparece se você testou o conflito)

-- 9) Invariantes (devem retornar ZERO linhas)
SELECT id_os FROM ordem_servico WHERE status = 'Pendente' AND id_tecnico_atribuido IS NOT NULL;      -- TR-08
SELECT id_os FROM ordem_servico WHERE status = 'Aberto';                                              -- TR-09
SELECT id_os FROM ordem_servico WHERE status = 'Finalizado' AND id_os NOT IN (SELECT id_os FROM custo_os);   -- custo congelado 100%
SELECT id_os FROM ordem_servico WHERE status IN ('Agendado','Em Atendimento','Pausado','Aguardando Reagendamento')
  AND id_tecnico_atribuido IS NULL AND NOT is_cancelled;                                              -- TR-08
SELECT visita_id FROM pausa WHERE is_ativa GROUP BY visita_id HAVING count(*) > 1;                    -- 1 pausa ativa por visita
SELECT id_os FROM visita WHERE NOT servico_finalizado GROUP BY id_os HAVING count(*) > 1;             -- ver nota abaixo
SELECT id_os, upper(numero_serie) FROM os_equipamento GROUP BY id_os, upper(numero_serie) HAVING count(*) > 1;   -- série única por OS
SELECT id_visita, id_os_equipamento FROM servico_equipamento WHERE id_os_equipamento IS NOT NULL
  GROUP BY id_visita, id_os_equipamento HAVING count(*) > 1;                                          -- 1 serviço por equipamento por visita
SELECT o.id_os FROM ordem_servico o
WHERE o.descricao_cliente LIKE 'TESTE-SMOKE-%' AND NOT EXISTS (SELECT 1 FROM os_equipamento e WHERE e.id_os = o.id_os);   -- OS de teste sem equipamento (RN-41)
SELECT s.id_servico, v.id_os FROM servico_equipamento s JOIN visita v ON v.id_visita = s.id_visita
JOIN ordem_servico o ON o.id_os = v.id_os
WHERE o.status = 'Finalizado' AND NOT s.is_legado AND v.atendimento_fim_em IS NOT NULL
  AND (s.conserto_salvo_em IS NULL
       OR NOT EXISTS (SELECT 1 FROM servico_foto f WHERE f.id_servico = s.id_servico AND f.tipo = 'conserto')
       OR NOT EXISTS (SELECT 1 FROM servico_foto f WHERE f.id_servico = s.id_servico AND f.tipo = 'defeito'));
                                                                         -- Finalizada: conserto salvo + foto de conserto + foto de defeito em cada serviço
-- (OS legadas anteriores à v0.5 podem aparecer nas duas últimas consultas até o backfill/vínculo do admin; filtre por TESTE-SMOKE-)

-- 10) Desativação (cenário 5): ação auditada, uma linha por OS afetada
SELECT id_os, papel, payload FROM log_acao WHERE acao = 'DESATRIBUIDA_POR_DESATIVACAO' ORDER BY id DESC LIMIT 10;

-- 11) Cancelamento
SELECT id_os, is_cancelled, motivo_cancelamento, cancelado_em, cancelado_por FROM ordem_servico WHERE is_cancelled ORDER BY id_os DESC LIMIT 5;
```

> Nota sobre o custo (consulta 2): no cenário 1 do smoke o total de materiais é **880** (850 + 2 × 15). Depois do cenário 8
> (correção do admin) o snapshot passa a **1.760** (+ 880) e `valores_utilizados` permanece idêntico ao do momento da
> finalização; compare `custo_os.total` com o `total_geral` devolvido por `GET /custos`.
>
> Nota sobre a invariante da visita aberta: após a desativação de um técnico no meio da visita (cenário 5) a visita
> antiga fica "abandonada" e **continua** `servico_finalizado=false` por desenho (histórico), então uma OS reatribuída pode
> aparecer ali com 2 visitas não finalizadas. Isso é esperado (só a visita mais recente é executável), não é bug.

---

## 7. Painel web (React/Vite — pasta `web/`)

```powershell
cd D:\Lucas\_Faculdade\7P\Jornada\Fast-Ariam---App-OS\web
npm install
npm run dev            # http://localhost:3000
```

O Vite faz proxy de `/api` e `/static` para `http://127.0.0.1:8000` (ou para `VITE_API_URL`, se definida em `web/.env`).
A API precisa estar no ar na porta 8000. (O `web/.env.example` pode listar também `DATABASE_URL`/`SECRET_KEY`: o painel **não**
usa essas variáveis; deixe só `VITE_API_URL` se precisar.) O painel é **online**: não há modo offline administrativo.

> Estes passos não foram executados na validação; os nomes de menus e botões vêm do código de `web/src`. Divergência de
> rótulo não é falha da API: registre e siga.

| # | Passo na tela | O que observar |
|---|---|---|
| 1 | Abra `http://localhost:3000` → e-mail/senha do admin → **Entrar no Sistema** | Entra no painel; credencial errada mostra "Não foi possível autenticar"; **sem** dados fictícios se a API cair (derrube a API e recarregue: deve aparecer erro, não números inventados) |
| 2 | Menu **Modelos de equipamento** → **Novo modelo** (`TESTE-SMOKE-MODELO-PAINEL`) | Aparece na lista; nome repetido (mudando só maiúsculas/espaços) dá erro claro (409); renomear funciona; desativar o modelo o tira da seleção de novas OS, **sem** apagar as OS que o usam |
| 3 | Menu **Gestão de Clientes** → cadastrar → **Cadastrar cliente** (razão social `TESTE-SMOKE-PAINEL`, código novo) | Aparece na lista; código repetido dá erro claro |
| 4 | **Equipe de Técnicos** → cadastrar → **Cadastrar técnico** (nome `TESTE-SMOKE-painel`, CPF/CNPJ válidos, dados bancários, senha ≥ 8) | Aparece na lista; **telefone não é preenchido por padrão** quando vazio |
| 5 | **+ Criar Nova OS** → cliente de teste, descrição `TESTE-SMOKE-painel ...`, **Equipamentos** (modelo + número de série; **Adicionar equipamento** para o 2º), deixar "Atribuir posteriormente (status: Pendente)" | **Criar ordem de serviço** fica **desabilitado** sem ao menos 1 equipamento completo (modelo e série); série repetida na mesma OS é recusada; com os dados corretos a OS nasce **Pendente** com os equipamentos listados no detalhe |
| 6 | Abra a OS → **Atribuir técnico** → escolha o técnico de teste | Vira **Agendado**; a visita aparece no detalhe |
| 7 | Detalhe da OS Agendada → seção de equipamentos → **Corrigir** (série e/ou modelo), **Adicionar equipamento**, **Remover** | Permitido até o início do atendimento; série duplicada dá erro; remover o **último** equipamento fica desabilitado/recusado; equipamento com foto de defeito não pode ser removido |
| 8 | No app (seção 8) execute ida, fotos de defeito e **Iniciar atendimento**. Recarregue o painel | Status acompanha (Em Atendimento); a seção de equipamentos passa a **somente leitura** (Corrigir/Adicionar/Remover bloqueados ou ausentes, com dica de que o atendimento já começou) |
| 9 | Com a OS **Em Atendimento**: **Pausar** → motivo "Outro" sem descrição | Erro local "a descrição é obrigatória"; com descrição → OS **Pausado**, autor "admin" |
| 10 | Com a OS **Pausado**: veja **Reagendar** | Desabilitado, com dica (precisa o técnico finalizar a volta) |
| 11 | No app, finalize a volta | OS vai a **Aguardando Reagendamento** |
| 12 | **Reagendar** → data de ontem | Recusado (422); data futura → OS **Agendado** com nova visita (que exige fotos de defeito de novo no app) |
| 13 | OS pendente de teste → **Cancelar OS** sem motivo | Recusado; com motivo → some da lista padrão e aparece em canceladas, com o motivo |
| 14 | OS **Finalizada** → detalhe | Custo mostrado como congelado (materiais, quilometragem, pedágio, frete, tempo, deslocamento); botão Cancelar **ausente**; "Serviços por equipamento" mostra modelo e série; equipamentos **sem** Corrigir/Adicionar/Remover |
| 15 | OS **Finalizada** → correção administrativa (fotos e materiais por equipamento): enviar nova foto de conserto, remover uma foto, tentar remover a **última** de um tipo; editar um material e salvar | Foto de conserto abaixo de 960x1280 é recusada; remover a última foto do tipo é recusado; ao salvar materiais o **custo congelado é recalculado** (total muda só pela diferença de materiais) e a OS continua Finalizada; confira as linhas `FOTO_CORRIGIDA_ADMIN`/`MATERIAIS_CORRIGIDOS_ADMIN` na seção 6 |
| 16 | **Equipe de Técnicos** → desativar o técnico de teste que tem OS Agendada | As OS dele voltam a **Pendente** sem técnico (equipamentos preservados); o técnico passa a **Inativo**; o app dele cai para o login (401) |
| 17 | Console do navegador (F12 → Network) | Nenhuma chamada fora de `/api` (desde a v0.6 a API não serve mais `/static`); nenhum 500; nenhum token na URL |

---

## 8. App Android (Expo — pasta `frontend/`)

```powershell
cd D:\Lucas\_Faculdade\7P\Jornada\Fast-Ariam---App-OS\frontend
npm install
# frontend/.env (não versionado):
#   EXPO_PUBLIC_API_URL=http://10.0.2.2:8000        # emulador Android (alias do host)
#   EXPO_PUBLIC_API_URL=http://<IP-do-PC>:8000      # aparelho físico na mesma rede (uvicorn com --host 0.0.0.0)
npx expo start --android
```

O app aceita a URL com ou sem `/api`. Use `http://` apenas em desenvolvimento; build de produção exige `https://`.
Se mudar o `.env`, reinicie com `npx expo start --clear`.

> Estes passos não foram executados na validação (o app compila, mas não foi rodado contra a API); os rótulos vêm do código
> de `frontend/src`. O técnico **não cadastra equipamento**: o app só mostra os equipamentos que o admin vinculou à OS.

| # | Passo na tela | O que observar |
|---|---|---|
| 1 | **Login** com o e-mail/senha do técnico de teste → **Entrar** | Entra em **Meus Chamados**; só as OS atribuídas a ele; senha errada mostra erro, não entra |
| 2 | Toque na OS Agendada | Detalhe com cliente, endereço ("Abrir no mapa") e a seção **EQUIPAMENTOS** com **os equipamentos da OS** (modelo + série, vindos do admin). **Não existe** botão "Adicionar equipamento" nem campo para digitar série ou nome |
| 3 | **Iniciar deslocamento (ida)** → informe o km (ex.: 1000) e **Tirar foto do odômetro** | Botão muda para **Finalizar deslocamento (ida)**; no painel a OS continua Agendado com ida iniciada |
| 4 | **Finalizar deslocamento (ida)** → km maior (1020) + foto | O botão **Iniciar atendimento** só habilita depois da foto de defeito de cada equipamento |
| 5 | Toque em **Iniciar atendimento** sem fotos (se o botão estiver habilitado, ou tente pela API) | Recusa com a lista de equipamentos pendentes ("Não é possível iniciar o atendimento…"); nada é iniciado |
| 6 | **Registrar Foto do Defeito** → (com 2+ equipamentos o app pergunta qual) → tire a foto pequena | Aceita (sem resolução mínima). Repita para **cada** equipamento; o card do equipamento passa a "Feito" |
| 7 | **Iniciar atendimento** | OS vira Em Atendimento (confirme no painel); aparecem **Pausar OS**, **Registrar Foto do Conserto**, **Registrar atendimento** por equipamento |
| 8 | Em cada equipamento: **Registrar atendimento** → defeito principal e sub-defeitos, material (nome, quantidade, valor) → **Salvar conserto** | Sem defeito principal o app/servidor recusa; o equipamento marca "conserto salvo". **Não há** campos de série/nome/modelo |
| 9 | **Registrar Foto do Conserto** com foto pequena | **Recusada** (mín. 960×1280 em qualquer orientação). Atenção: a câmera do **emulador** costuma gerar imagem pequena; para o caso positivo coloque uma imagem grande na galeria do emulador ou use um aparelho físico |
| 10 | Tente **Finalizar atendimento** com algum equipamento sem conserto salvo ou sem foto de conserto | Botão desabilitado ou erro 409 listando o que falta (modelo/série pendente); só libera com os **dois** requisitos em **todos** os equipamentos |
| 11 | (opcional) **Pedágio e frete**: valor > 0 sem foto do comprovante → **Salvar** | O app pede o comprovante ("Anexe o comprovante do pedágio"); a API ainda revalida na finalização da volta (400 sem comprovante) |
| 12 | **Finalizar atendimento** → nome do cliente, CPF `111.111.111-11`, assinatura | CPF inválido recusado; com `529.982.247-25` e assinatura desenhada, segue |
| 13 | **Iniciar deslocamento (volta)** → km 1020 + foto; **Finalizar deslocamento (volta)** → km 1040 + foto de fim | Mensagem **OS finalizada**; sem botões de ação |
| 14 | Painel/Swagger: `GET /api/chamados/{os}/custos` | `congelado=true` |
| 15 | **Pausa pelo técnico** (outra OS): depois de **Iniciar atendimento**, **Pausar OS** → motivo | Pausar **não** exige conserto salvo nem foto de conserto; o botão de finalizar atendimento some; só resta a volta; ao finalizar a volta aparece **Aguardando reagendamento** |
| 16 | Admin reagenda a OS pausada; no app abra a **visita nova** | As exigências recomeçam: fotos de defeito de novo antes de iniciar o atendimento; conserto salvo + foto de conserto antes de finalizar |
| 17 | **Offline**: ative o modo avião no meio de uma OS e execute ida, foto de defeito, início de atendimento, conserto e assinatura | As ações ficam **guardadas no aparelho** (indicador de pendentes na lista); feche e reabra o app: a fila continua. Desative o modo avião e puxe para atualizar/sincronize: as pendências são enviadas (`/api/sync/arquivos` e `/api/sync/eventos`); no painel a OS acompanha. Reenviar/sincronizar de novo **não** duplica nada |
| 18 | Offline: o admin cancela ou reatribui a OS enquanto o aparelho está sem rede, depois sincronize | Os eventos dessa OS voltam como rejeitados (`OS_CANCELADA`/`OS_REATRIBUIDA`) e o app não perde a fila nem apaga arquivos; em conflito administrativo a OS vai a **Pendente** sem técnico |
| 19 | Sessão offline: o app aceita ações offline por até 24 h desde o último login **online**; passado esse prazo mostra **Sessão offline encerrada** → **Entrar novamente** | A fila **nunca** é apagada; ao entrar de novo com a mesma conta e com internet, ela é enviada |
| 20 | Admin desativa o técnico no painel; no app toque em qualquer ação ou em atualizar | Sessão cai para o login; nada de dados antigos acessível (e a fila pendente só é enviada ao entrar de novo com a conta) |

---

## 9. Limpar os dados de teste

Faça **depois** de terminar o painel e o app (as OS que você criou lá também usam o prefixo, se você seguiu o roteiro).

1. **Anote os arquivos** (somente leitura) e apague-os do disco depois:
   ```sql
   SELECT assinatura_url, foto_inicio_ida_url, foto_fim_ida_url, foto_inicio_volta_url, foto_fim_volta_url
   FROM visita WHERE id_os IN (SELECT id_os FROM ordem_servico WHERE descricao_cliente LIKE 'TESTE-SMOKE-%');
   SELECT url FROM servico_foto WHERE id_servico IN (SELECT id_servico FROM servico_equipamento WHERE id_visita IN
     (SELECT id_visita FROM visita WHERE id_os IN (SELECT id_os FROM ordem_servico WHERE descricao_cliente LIKE 'TESTE-SMOKE-%')));
   SELECT url FROM sync_arquivo WHERE id_os IN (SELECT id_os FROM ordem_servico WHERE descricao_cliente LIKE 'TESTE-SMOKE-%');
   ```
   Desde a v0.6 os arquivos ficam no bucket privado do Supabase Storage (`uploads/chamado_<id>_*` e `assinaturas/*.enc`;
   assinaturas têm nome aleatório, cruze pelos URLs acima). Só com Storage local (dev/teste, sem `SUPABASE_URL`) eles ficam em
   `backend/static/uploads` e `backend/static/assinaturas`, ou nas pastas de `UPLOAD_DIR`/`ASSINATURA_DIR`, se definidas.
2. **Opção rápida (desativar em vez de apagar)** — se você prefere preservar a auditoria:
   ```sql
   UPDATE tecnico SET is_active = false WHERE nome LIKE 'TESTE-SMOKE-%';
   UPDATE cliente SET is_active = false WHERE razao_social LIKE 'TESTE-SMOKE-%';
   UPDATE equipamento_modelo SET is_active = false WHERE modelo LIKE 'TESTE-SMOKE-%';
   ```
   (Isto **não** desatribui OS; use o `DELETE /api/tecnicos/{id}` da API se houver OS ativas. Modelos desativados somem da
   seleção de novas OS, mas continuam no catálogo.)
3. **Apagar tudo por prefixo** (SQL Editor; revise com `ROLLBACK` primeiro, depois troque por `COMMIT`). A ordem respeita as
   FKs da v0.5 (`servico_equipamento` antes de `os_equipamento`; `sync_evento`/`sync_arquivo` antes de `visita`;
   `os_equipamento` antes de `equipamento_modelo`). Este script é a adaptação para Postgres do SQL que o smoke imprime (esse
   foi executado e conferido em SQLite com chaves estrangeiras ligadas: apagou tudo e preservou o admin); confira a sintaxe
   no ensaio com `ROLLBACK`:

   ```sql
   BEGIN;

   CREATE TEMP TABLE _smoke_cli ON COMMIT DROP AS SELECT id_cliente FROM cliente WHERE razao_social LIKE 'TESTE-SMOKE-%';
   CREATE TEMP TABLE _smoke_tec ON COMMIT DROP AS SELECT id_tecnico FROM tecnico WHERE nome LIKE 'TESTE-SMOKE-%';
   CREATE TEMP TABLE _smoke_os  ON COMMIT DROP AS SELECT id_os FROM ordem_servico
     WHERE descricao_cliente LIKE 'TESTE-SMOKE-%'
        OR id_cliente IN (SELECT id_cliente FROM _smoke_cli)
        OR id_tecnico_atribuido IN (SELECT id_tecnico FROM _smoke_tec);
   CREATE TEMP TABLE _smoke_vis ON COMMIT DROP AS SELECT id_visita FROM visita WHERE id_os IN (SELECT id_os FROM _smoke_os);
   CREATE TEMP TABLE _smoke_srv ON COMMIT DROP AS SELECT id_servico FROM servico_equipamento WHERE id_visita IN (SELECT id_visita FROM _smoke_vis);
   CREATE TEMP TABLE _smoke_mod ON COMMIT DROP AS SELECT id_equipamento_modelo FROM equipamento_modelo WHERE modelo LIKE 'TESTE-SMOKE-%';

   -- Confira ANTES de apagar: tudo abaixo deve ser dado de teste.
   SELECT 'os' AS tipo, count(*) FROM _smoke_os UNION ALL SELECT 'tecnicos', count(*) FROM _smoke_tec
   UNION ALL SELECT 'clientes', count(*) FROM _smoke_cli UNION ALL SELECT 'modelos', count(*) FROM _smoke_mod;
   -- Um modelo de teste usado por uma OS que NÃO é de teste faria o DELETE de equipamento_modelo falhar (FK RESTRICT): ótimo, nada é apagado em silêncio.

   DELETE FROM material            WHERE id_servico IN (SELECT id_servico FROM _smoke_srv);
   DELETE FROM servico_foto        WHERE id_servico IN (SELECT id_servico FROM _smoke_srv);
   DELETE FROM servico_defeito     WHERE id_servico IN (SELECT id_servico FROM _smoke_srv);
   DELETE FROM servico_equipamento WHERE id_servico IN (SELECT id_servico FROM _smoke_srv);
   DELETE FROM comprovante         WHERE id_visita IN (SELECT id_visita FROM _smoke_vis);
   DELETE FROM pausa               WHERE visita_id IN (SELECT id_visita FROM _smoke_vis)
                                      OR por_usuario_id IN (SELECT id_tecnico FROM _smoke_tec);
   DELETE FROM sync_evento         WHERE id_os IN (SELECT id_os FROM _smoke_os)
                                      OR id_tecnico IN (SELECT id_tecnico FROM _smoke_tec);
   DELETE FROM sync_arquivo        WHERE id_os IN (SELECT id_os FROM _smoke_os)
                                      OR id_tecnico IN (SELECT id_tecnico FROM _smoke_tec);
   DELETE FROM log_acao            WHERE id_os IN (SELECT id_os FROM _smoke_os)
                                      OR id_usuario IN (SELECT id_tecnico FROM _smoke_tec)
                                      OR (id_os IS NULL AND acao LIKE 'EQUIPAMENTO_MODELO_%' AND CAST(payload AS TEXT) LIKE '%TESTE-SMOKE-%');
   DELETE FROM custo_os            WHERE id_os IN (SELECT id_os FROM _smoke_os);
   DELETE FROM visita              WHERE id_visita IN (SELECT id_visita FROM _smoke_vis);
   DELETE FROM os_equipamento      WHERE id_os IN (SELECT id_os FROM _smoke_os);
   DELETE FROM ordem_servico       WHERE id_os IN (SELECT id_os FROM _smoke_os);
   DELETE FROM equipamento_modelo  WHERE id_equipamento_modelo IN (SELECT id_equipamento_modelo FROM _smoke_mod);
   DELETE FROM tecnico             WHERE id_tecnico IN (SELECT id_tecnico FROM _smoke_tec);
   DELETE FROM cliente             WHERE id_cliente IN (SELECT id_cliente FROM _smoke_cli);

   ROLLBACK;   -- ensaio. Depois de conferir as contagens, troque por COMMIT;
   ```

   O smoke também imprime ao final uma versão do SQL com os **ids exatos** da execução (mais restritiva; prefira-a se
   houver outros dados `TESTE-SMOKE-` que você queira manter).
4. **Verifique** que não sobrou nada: `SELECT count(*) FROM tecnico WHERE nome LIKE 'TESTE-SMOKE-%';` (e idem para cliente,
   `equipamento_modelo.modelo` e `ordem_servico.descricao_cliente`) e que os indicadores do painel voltaram ao normal.
5. As sequências de ids (`ordem_servico_id_os_seq` etc.) **não voltam atrás**: haverá "buracos" na numeração. É esperado e inofensivo.
6. Apague `backend/defeito.jpg`, `conserto_*.jpg`, `assinatura.png`, `nao_e_imagem.jpg`, `grande.jpg` e a saída do smoke, se salvou.

---

## 10. Riscos de rodar contra o banco real

| # | Risco | Impacto | Mitigação |
|---|---|---|---|
| 1 | Dev e produção no mesmo Supabase (risco aceito pelo PO, SEG-05/12/19) | Dados de teste ficam misturados aos reais; listas e indicadores do painel/app mostram OS, clientes, técnicos e **modelos de equipamento** de teste | Prefixo `TESTE-SMOKE-`; rodar em horário sem uso; limpar logo (seção 9); avisar a equipe |
| 2 | Contas de técnico de teste **ativas** com senha aleatória (não impressa) | Contas válidas sem dono até a limpeza | Limpar/desativar logo; o smoke gera a senha aleatória por execução e não a exibe |
| 3 | O cenário 5 **desativa** técnicos e **desatribui OS** | Se o script fosse apontado para um técnico real, OS reais voltariam a Pendente | O script só desativa técnicos que ele mesmo criou; no roteiro manual/painel use **apenas** `TESTE-SMOKE-` |
| 4 | Arquivos de teste gravados no **bucket privado** do Supabase Storage (v0.6; antes, no disco da API servido por `/static`) | Sobram objetos órfãos no bucket após a limpeza do banco; a suíte automatizada não pode herdar `SUPABASE_*` (o `conftest.py` aborta se o armazenamento não for local) | Imagens são sintéticas (sem dados pessoais); remova os objetos de teste do bucket (seção 9); não exponha a API à internet durante o teste |
| 5 | Linhas em `log_acao` (auditoria), `custo_os`, `sync_evento` e `sync_arquivo` | Poluem a trilha e métricas de custo | O SQL de limpeza apaga as linhas das OS de teste; só faça isso para dados de teste |
| 6 | Credenciais do admin em variável de ambiente / histórico | Vazamento da senha | Use `Read-Host -AsSecureString`, remova a variável ao fim, troque a senha se ela foi digitada num lugar visível |
| 7 | `SECRET_KEY` nova | Invalida todos os tokens existentes (sessões de painel e app) | Esperado; avise a equipe |
| 8 | Concorrência com usuários reais | O smoke usa só dados próprios, mas compartilha o banco: picos de conexão no plano Free | Janela sem uso; o script é sequencial |
| 9 | Upload de ~15 MB | Consome egress/banda, demora em conexão lenta | `SMOKE_SKIP_BIG_UPLOAD=1` se necessário |
| 10 | Projeto Free do Supabase **pausado** por inatividade | A API não conecta | Reativar no painel e aguardar |
| 11 | Sequências de id e `codigo` de cliente consumidos | Buracos na numeração; `codigo` aleatório entre 1,5 e 2,1 bilhão pode colidir com um código real futuro | A faixa fica longe dos códigos reais; apagar os clientes de teste libera o código |
| 12 | Execução do script apontando para a URL errada | Dados criados em outro ambiente | Confira o `alvo:` impresso na 1ª linha antes do primeiro passo |
| 13 | `resetar_banco.py` / `AUTO_CREATE_TABLES=true` no `.env` real | **Perda total de dados** | Nunca rode o reset; mantenha `AUTO_CREATE_TABLES=false` |
| 14 | SQL de limpeza com filtro largo | Apagar dados reais | Os filtros exigem `TESTE-SMOKE-%`; use primeiro o ensaio com `ROLLBACK` e confira as contagens |
| 15 | Modelos de teste ficam no catálogo (a API só desativa, nunca exclui) | O admin real vê modelos `TESTE-SMOKE-…` ao criar OS | Desative-os (seção 9, item 2) ou apague por SQL; o painel só lista ativos na criação de OS |
| 16 | Schema sem as migrações `0007`/`0009` | 500 nas rotas de OS/equipamento/sync; o smoke cria dados parciais (cliente, técnicos) antes de falhar | Rode a consulta 0 da seção 6 antes; se faltar, aplique as migrações pelo fluxo do DBA (README das migrações) |

---

## 11. Achados da validação local (leia antes de interpretar o resultado)

1. **Backend: nenhum defeito encontrado** na execução do smoke v0.5 (378 passos OK, 0 falhas, contra SQLite temporário). O
   achado da versão anterior deste roteiro (serviços criados/alterados em OS `Finalizado`) **não se aplica mais**: agora o
   técnico recebe 409 em PATCH/foto/salvar-conserto de OS Finalizada, `POST .../servicos` responde 410 e só o admin corrige
   fotos e materiais (RN-49), com custo recalculado.
2. **[Baixo] `seed.py` e o CNPJ marcador UNIQUE**: criar um segundo admin com o seed falha se o primeiro foi criado pelo
   próprio seed (seção 3).
3. **Limitações do SQLite (o que a validação local NÃO prova)**:
   - Os CHECKs com `btrim`/regex (`ck_equipamento_modelo_modelo`, `ck_os_equipamento_numero_serie`, `documento_cliente`…) não existem
     no SQLite; para criar o schema ali é preciso removê-los do metadata (o `tests/conftest.py` faz o mesmo). Por isso série/modelo
     com espaços nas pontas e o regex do CPF só são provados em Postgres (a camada Pydantic já normaliza antes do banco).
   - `SELECT ... FOR UPDATE` (`lock_chamado`, desativação de técnico) é ignorado pelo SQLite: **concorrência** (duas ações simultâneas na
     mesma OS, reenvio simultâneo do mesmo `client_event_id`/`client_file_id`) não foi exercitada.
   - ENUM, JSONB, `TIMESTAMPTZ` (o SQLite devolve datas sem fuso), UUID nativo, índices únicos funcionais
     (`lower(modelo)`, `upper(numero_serie)`) e FKs `RESTRICT` dependem de `PRAGMA foreign_keys`; devem ser confirmados no Supabase.
   - O SQL de limpeza foi executado no SQLite com FKs ligadas (ordem e nomes de colunas conferidos); a sintaxe Postgres
     (`CREATE TEMP TABLE ... ON COMMIT DROP`, `CAST(payload AS TEXT)`) deve ser conferida no ensaio com `ROLLBACK`.
   Se algo falhar **só** no Supabase, comece por aí e por migrações incompletas (`0000_inventario.sql` e a consulta 0 da seção 6).
4. **Não cobertos pelo smoke**: telas do painel e do app (seções 7 e 8, a executar manualmente), fila/outbox do aparelho (reabertura do
   app, 24 h offline, JWT expirado), conflito administrativo com a pausa do admin durante o offline (`CONFLITO_ADMINISTRATIVO`, coberto
   só pelos testes do repositório) e desempenho/carga. O Storage privado (SEG-09) foi implementado na v0.6 e verificado manualmente em
   11/11/2026 (link público 404, sem token 401, outro técnico 403, admin 200).
