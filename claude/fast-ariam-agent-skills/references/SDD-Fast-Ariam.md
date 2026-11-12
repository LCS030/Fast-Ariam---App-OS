# SDD — Fast Ariam: Especificação Técnica Orientada a Especificação

| Campo | Valor |
|---|---|
| Versão | 0.6 (confidencialidade e integridade de 08/11/2026 incorporadas sobre a v0.5 de 08/11/2026 e a v0.4 de 07/11/2026) |
| Data | 08/11/2026 |
| Documento de requisitos | `PRD-Fast-Ariam.md` v0.5 (referências RF-xx, RN-xx, PR-xx, CA-xx) |
| Repositórios | Backend e app: `LCS030/fast-ariam---app-os` · Painel: `Jonathan-Ferreira-Berdusco/Fast-IA-Studio` |

> **v0.5 (08/11/2026).** **Situação da implementação (08/11/2026):** backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 346 testes automatizados em SQLite e um smoke ponta a ponta (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), mas o backend novo ainda NÃO foi executado contra esse PostgreSQL; painel web (`web/`) e app do técnico (`frontend/`, com outbox offline) implementados, `tsc` sem erros, mas NÃO executados em navegador/aparelho nem contra o backend; nenhum controle SEG-xx foi verificado em PostgreSQL. As seções marcadas "v0.5" (0.2, 3, 4.5, 4.8, 4.9, 5, 6.5 a 6.7, 6.12, 6.13, 7, 8, 10, 11 e 12) descrevem o contrato da regra de equipamento da OS: catálogo de modelos, vínculo modelo + número de série na OS e travas de foto de defeito e de conserto. As interpretações do detalhamento foram confirmadas pelo responsável em 08/11/2026 (PRD 11.1.2); também foram confirmados, em 08/11/2026, o **recálculo do custo** na correção de materiais pós-finalização (com os valores congelados, 6.13) e que **somente fotos e materiais** são editáveis após a finalização. Não restam pontos em aberto na regra de equipamento.

> **v0.6 (08/11/2026) — Confidencialidade e Integridade.** **Situação da implementação:** backend com **414 testes automatizados em SQLite** passando (os 346 da v0.5 mais 68 novos, em `tests/chamados/test_cifragem_integridade.py`, `test_storage_privado.py` e `test_migracao_storage.py`); painel (`web/`) e app (`frontend/`) com `tsc` sem erros, **sem execução em navegador nem em aparelho**. As migrações `0010` (hash e selo), `0011` (cifragem) e `0012` (`cnpj_idx` obrigatório) foram **aplicadas no Supabase real em 08/11/2026 pelo MCP**, depois de um backup íntegro (`scripts/backup_banco.py`), e os dados existentes foram cifrados por `scripts/cifrar_dados_existentes.py`. O resultado foi **conferido por consulta SQL** (nenhum CPF/CNPJ/telefone/dado bancário em claro; índices cegos preenchidos; 2 assinaturas `.enc`) e por uma **leitura somente-leitura do backend novo contra o banco real** (decifragem e recálculo do índice cego corretos; as 2 OS existentes aparecem como `sem_selo`). **Mesmo assim, a API completa não foi exercitada contra o PostgreSQL** e nenhum controle SEG-xx é tratado como *verificado*. Seção nova **8.1** (decisões criptográficas, chaves, matriz dos quatro pilares, riscos residuais), SEG-22 a SEG-28, testes T-60 a T-99 (11.2) e T-100 a T-112 (11.3) e backlog 31 a 36. Sobre a assinatura: **a imagem da assinatura não é assinatura digital e não fornece não repúdio criptográfico** (8.1).

> **Atualização de 11/11/2026 (v0.6.1) — verificações no ambiente real.** Conferidos diretamente no Supabase e na API em execução: **RLS** ligado em todas as 17 tabelas de `public` (`pg_class.relrowsecurity = true`) e **nenhuma política** em `pg_policies`, portanto `anon`/`authenticated` não acessam dados (SEG-12, SEG-20); **TLS até o banco** com `DB_SSLMODE=verify-full` e `DB_SSLROOTCERT=certs/prod-ca-2021.crt` (TLSv1.3, `TLS_AES_256_GCM_SHA384`), com recusa de certificado inexistente e recusa, pelo próprio servidor, de conexão com `sslmode=disable` (SEG-27); **HSTS** presente nas respostas da API com `ENV=production`, servida por um túnel HTTPS temporário (SEG-27). Também foram exercitados contra o ambiente real: storage privado (401/403/200), JWT adulterado (401), upload com hash divergente (422 `HASH_DIVERGENTE`), selo da visita (`integro` → `selo_divergente` → `selo_removido`) e cifra adulterada (500, decifragem recusada). HTTPS no deploy definitivo e build Android de produção continuam não verificados.

> Este documento define o contrato técnico entre banco, API, painel e app. É a referência de implementação e testes e deve permanecer sincronizado com o PRD v0.5. O código atual é evidência de implementação, não substitui o contrato. Não há decisão de negócio bloqueante em aberto: a RN-08a (desativação de técnico) foi resolvida em 07/11/2026. Itens marcados "implementado" referem-se ao backend e foram exercitados **apenas por testes automatizados em SQLite**; nada foi verificado contra PostgreSQL/Supabase nem validado pelo QA (ver seção 8).

---

## 0. Decisões incorporadas na v0.3

| Decisão | Impacto técnico | Seção |
|---|---|---|
| Reagendamento em `Pausado` proibido até finalizar a volta | Reagendamento só em `Aguardando Reagendamento` ou `Agendado` antes da ida | 5, 6.10 |
| Reagendar `Agendado` antes da ida altera a visita existente | Não criar visita vazia | 5, 6.10 |
| `Pendente` = OS não finalizada sem técnico | Criação sem técnico e conflitos offline levam a Pendente; `Aberto` é legado | 4, 5, 6.5 |
| Conflito offline com ação administrativa incompatível | Rejeitar ações conflitantes, desatribuir técnico e mover OS não finalizada para Pendente; registrar auditoria | 5, 6.12 |
| Custo global do sistema | Configuração central sem valores individuais por técnico; remover endpoints de configuração do técnico | 3, 4.7, 6.11 |
| Congelar custo na finalização | Persistir snapshot em `custo_os` com valores globais utilizados | 4.7, 6.11 |
| Sessão offline até 24 horas | Sem refresh token; preservar fila e exigir novo login online ao expirar/atingir limite | 6.12, 8 |
| Upload máximo de 15 MB por imagem | Validar no app, API e bucket | 6.8, 7, 8, 9 |
| Fotos estão no disco do servidor | Migrar para Supabase Storage com bucket privado | 1, 9 |
| Supabase Storage Free | Bucket privado disponível dentro da cota Free; monitorar 1 GB de storage/5 GB egress e risco de pausa do projeto | 9 |
| Metas de performance | p95 de API ≤ 2 s; upload de 15 MB ≤ 30 s em rede de referência | PRD RNF-05, testes |
| Ajudantes e notificações | Fora do escopo; não criar UI, endpoints ou custos associados | PRD seção 5 |
| Política de desativação de técnico | **Resolvida na v0.4 (RN-08a):** invalida a sessão e desatribui todas as OS não finalizadas e não canceladas (→ `Pendente`), com auditoria | 3, 5, 6.3, 8 |

As demais decisões previamente confirmadas permanecem válidas: motivos de pausa, pausa pelo admin durante atendimento, assinatura por visita com CPF, cancelamento com motivo e sem cancelamento de OS finalizada, apenas Android, banco acessado exclusivamente pela API e operação offline-first.

### 0.1 Decisões do PO e contratos da v0.4 (07/11/2026)

**Decisões do PO**

| Decisão | Impacto técnico | Seção |
|---|---|---|
| RN-08a resolvida | `DELETE /api/tecnicos/{id}` desativa e, na mesma transação, move para `Pendente` (sem técnico) todas as OS do técnico não finalizadas e não canceladas; visitas, fotos, serviços e pausas preservados (pausas ativas são encerradas); Finalizadas/canceladas intactas; auditoria em `log_acao` | 5.1, 6.3, T-17 |
| Visita automática | Toda OS que entra em `Agendado` ganha uma visita aberta na mesma transação; `data_visita` = `data_agendamento` ou hoje (America/Sao_Paulo); `POST .../visitas` com visita não finalizada existente → 409 | 5.1, 6.5.3 |
| CPF/CNPJ | Técnico: CPF (14) e CNPJ (18) com máscara canônica. Cliente na visita: CPF só dígitos (11) | 4.1, 4.7, 6.3.1, 7 |
| Admin não recebe OS | Só o papel `tecnico` (ativo) é atribuível | 3, 6.5.3 |
| Tempo de serviço de visita pausada = 0 no custo | Regra do cálculo e do snapshot | 6.11 |
| Foto de conserto em qualquer orientação | menor lado ≥ 960 e maior lado ≥ 1280 | 6.7, 6.8, 7, T-08 |
| Ambiente compartilhado | Dev e produção no mesmo projeto Supabase: risco aceito pelo PO, com ressalva de SEG | 2, 8 |

**Contratos alterados no código e agora refletidos aqui (implementados no backend)**

| Contrato | Seção |
|---|---|
| `ocorrido_em` opcional nos payloads de iniciar/finalizar deslocamento, iniciar-atendimento, pausar e finalizar-atendimento | 6.6.4 |
| `Visita` devolve `assinatura_url`, `nome_cliente_assinatura`, `documento_cliente`, os seis `*_em` e `pausas[]` | 6.6.5 |
| `finalizar-dados` responde 410; `POST /concluir` e `DELETE /chamados/{id}` removidos | 6.5, 6.6 |
| `PATCH` da OS: técnico sempre 403; `status` não é livre | 3, 6.5 |
| Reagendar: data passada → 422; exige técnico ativo → 409 | 6.10 |
| Uploads: OS Finalizada → 409; limite 15 MB → 413; formato real JPEG/PNG → 422 | 6.8 |
| `GET /custos` devolve `congelado`, `calculado_em`, `valores_utilizados` | 6.11 |
| `GET /api/auth/me` existe | 6.2 |
| Configuração: `CORS_ORIGINS`, `ENV`, `AUTO_CREATE_TABLES`, `SECRET_KEY` ≥ 32 caracteres em produção; `/static` com `nosniff` | 2, 8 |

### 0.2 Regra de equipamento da OS e decisões técnicas da v0.5 (08/11/2026)

**Decisão do responsável (PRD 11.1.2):** o técnico não cadastra equipamento; o administrador mantém um catálogo de modelos e vincula modelo + número de série na OS (um ou mais); o técnico não edita equipamento nem série; atendimento só inicia com foto do defeito e só finaliza com conserto salvo e foto do conserto.

**Decisões técnicas aplicadas (propostas pelos agentes DBA/Backend/Frontend/QA; reversíveis até a implementação)**

| Decisão | Impacto técnico | Seção |
|---|---|---|
| Catálogo `equipamento_modelo` e vínculo `os_equipamento` (modelo + série, único por OS) | Duas tabelas novas; `ChamadoCreate` com `equipamentos[]` (mín. 1); CRUD admin | 4.8, 6.13 |
| O servidor cria **um registro `servico_equipamento` por equipamento da OS** ao abrir a visita (e ao vincular equipamento com visita aberta) | O técnico nunca cria equipamento nem serviço; resolve a âncora da foto de defeito antes de iniciar o atendimento. `POST .../servicos` passa a responder **410** | 6.5.3, 6.7 |
| `servico_equipamento.id_os_equipamento` + `conserto_salvo_em` + `is_legado` | Vínculo ao equipamento da OS; marca explícita de "conserto salvo"; legado identificável | 4.5, 4.9 |
| Travas no **serviço** (não só no router), em transação | `iniciar-atendimento` exige foto de defeito por equipamento; `finalizar-atendimento` exige conserto salvo + foto de conserto por equipamento; **HTTP 409** com pendências | 5.3, 6.6, 6.7 |
| Exigências **por equipamento e por visita** | Visita 2 repete foto de defeito e conserto | 6.6, 6.13 |
| `GET .../estado` devolve `equipamentos[]` e motivos de bloqueio | App não decide sozinho | 6.6.3 |
| Edição de equipamento pelo admin só até o início do atendimento da visita vigente; **volta apenas com a OS Finalizada**, restrita a fotos comprobatórias e materiais (RN-49) | Evita mudar o escopo em campo; auditoria em `log_acao` com antes/depois; o custo é recalculado com os valores congelados (6.11, 6.13) | 6.13 |
| OS sempre com ao menos um equipamento (RN-41, RN-46) | 422 na criação; OS legada sem equipamento não pode ser atribuída, reagendada nem iniciada (TR-15) | 5.3, 6.13 |
| Catálogo legível somente pelo admin; o técnico recebe os equipamentos embutidos na OS | Menor privilégio | 3, 6.13 |
| Rejeições offline `FOTO_DEFEITO_AUSENTE` e `CONSERTO_INCOMPLETO` | Contrato-alvo de `/api/sync` (ainda não implementado) | 6.12 |
| Migração em fases (expandir, backfill, contrair) com `is_legado` | Dev e produção compartilham o mesmo banco (risco aceito): ensaiar em dump restaurado | 4.9 |

### 0.3 Decisões técnicas da v0.6 — Confidencialidade e Integridade (08/11/2026)

Decisões tomadas pelo responsável do projeto em 08/11/2026 (os agentes propuseram; o responsável aprovou e implementou o plano). Detalhes e justificativas na seção 8.1.

| Decisão | Impacto técnico | Seção |
|---|---|---|
| **D1** Selo de integridade **por visita**, gravado em `finalizar-atendimento`; cobre o que fica fechado nesse momento; correção administrativa pós-finalização **resseala** a visita e audita | `visita.selo_integridade` / `selo_versao`; `GET /api/chamados/{id}/verificar-integridade` | 4.4, 6.6, 8.1 |
| **D2** Hash das fotos de odômetro/deslocamento em uma coluna JSON da visita | `visita.arquivos_sha256` | 4.4 |
| **D3** O servidor **sempre** calcula e grava o SHA-256; o hash calculado no aparelho é **obrigatório** (`SHA256_ORIGEM_OBRIGATORIO=true`, app ainda não distribuído) | Todo upload exige `sha256`; sem ele, 422 `HASH_AUSENTE` | 6.8, 6.12 |
| **D4** Visitas finalizadas **antes** do selo ficam `sem_selo`; não há selagem retroativa | Estado `sem_selo` não é adulteração | 8.1 |
| **D5** Campos cifrados: CPF do cliente na visita e CPF, CNPJ, telefone e dados bancários/PIX do **técnico**. Telefones do **cliente** (comerciais) e **e-mail** ficam em claro | `TextoCifrado`; e-mail é a chave de login | 4.1, 4.4, 8.1 |
| **D6** Formato `enc1:<base64(nonce‖ciphertext‖tag)>`, AAD = `fast-ariam-v1|<tabela.coluna>` | Migração idempotente, rotação futura (`enc2:`), valor não reutilizável em outra coluna | 8.1 |
| Assinatura em disco **cifrada** (`.enc`) e servida **somente** por rota autenticada; `/static/assinaturas` deixa de existir | SEG-09 parcial: **fotos e comprovantes também em bucket privado** (seção 9) | 6.6, 9 |
| TLS: `sslmode` obrigatório até o banco, HSTS em produção, Android sem tráfego HTTP puro por padrão | `DB_SSLMODE`, `app.config.ts` | 2, 8.1 |

## 1. Arquitetura

```
┌──────────────────────┐        ┌──────────────────────┐
│ Painel admin (web)   │        │ App do técnico       │
│ React 18 + Vite + TS │        │ Expo 54 + RN 0.81    │
│ Recharts, Tailwind 4 │        │ axios, expo-router   │
└──────────┬───────────┘        └──────────┬───────────┘
           │  HTTPS / JSON / multipart      │
           │  Authorization: Bearer <JWT>   │
           ▼                                ▼
┌─────────────────────────────────────────────────────────┐
│ API FastAPI (app.main:app), prefixo /api                 │
│ routers: auth, tecnicos, clientes, chamados, equipamentos│
│ core/security (JWT, bcrypt, RBAC)                        │
│ services: chamado, custo, file                           │
│ repositories: SQLRepository (SQLAlchemy 2.0)             │
└───────────────┬───────────────────────────┬─────────────┘
                │ DATABASE_URL (psycopg2)    │ API / service key
                ▼                            ▼
┌───────────────────────────┐   ┌─────────────────────────────┐
│ PostgreSQL (Supabase)     │   │ Supabase Storage            │
│ tabelas da seção 4        │   │ bucket privado (alvo v0.3)  │
└───────────────────────────┘   └─────────────────────────────┘
```

**Regras de arquitetura**

- **AR-01** Os dois fronts só falam com a API. Nenhum deles usa o SDK do Supabase.
- **AR-02** Toda regra de negócio fica no backend. O front pode esconder botões com base em `GET .../estado`, mas não é a única barreira.
- **AR-03** Todas as rotas exceto `POST /api/auth/login` e `GET /` exigem Bearer JWT.
- **AR-04** O app do técnico é **offline-first**: toda ação grava primeiro no aparelho e é enviada depois. O servidor continua sendo a fonte de verdade e revalida cada ação (seção 6.12).
- **AR-05** O horário de uma ação é sempre o do aparelho no momento em que ela ocorreu, guardado com data e fuso. O servidor registra também o horário de recebimento.
- **AR-06** Toda ação que muda estado aceita um identificador gerado pelo cliente (`client_event_id`) e é idempotente.
- **AR-07** Arquivos persistentes ficam em bucket privado do Supabase Storage; painel e app acessam os arquivos somente por intermédio da API, que verifica a autorização e emite URL assinada curta.
- **AR-08** A sessão local do app pode autorizar operação offline por até 24 horas após a última autenticação online bem-sucedida. Não existe refresh token.
- **AR-09** *(v0.5)* O equipamento pertence à **OS** (`os_equipamento`), não à visita nem ao técnico. As pré-condições de início e de finalização do atendimento (foto de defeito; conserto salvo + foto de conserto) são validadas **no serviço, dentro da transação**, e valem igualmente para o endpoint online e para os eventos de `/api/sync`. Nenhum front é autoridade dessas regras.

## 2. Stack e versões

| Camada | Tecnologia | Versão (fonte) |
|---|---|---|
| API | FastAPI | 0.121.1 |
| Validação | Pydantic | 2.12.4 |
| ORM | SQLAlchemy | 2.0.44 |
| Driver | psycopg2-binary | 2.9.11 |
| Auth | python-jose (JWT HS256), bcrypt | 5.0.0 |
| Imagens | Pillow | 12.1.1 |
| Servidor | uvicorn | 0.38.0 |
| Painel | React 18.3, Vite 6, TypeScript 5.7, lucide-react 0.475, Recharts 3.10 | `package.json` |
| App | Expo ~54.0.23, React Native 0.81.5, React 19.1, expo-router ~6.0.14, axios ^1.13.2, expo-image-picker ~17.0.8, react-native-signature-canvas ^5.0.1 | `frontend/package.json` |

**Configuração (variáveis de ambiente do backend)**

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `DATABASE_URL` | Sim | — | String de conexão SQLAlchemy (`postgresql+psycopg2://...`) |
| `SECRET_KEY` | Sim | — | Assinatura do JWT. Sem ela, a aplicação não inicia. Com `ENV=production` exige **≥ 32 caracteres** (abaixo disso não inicia; fora de produção apenas avisa) |
| `ALGORITHM` | Não | `HS256` | Algoritmo do JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Não | `30` | Validade do token |
| `CORS_ORIGINS` | Sim em produção | — | Origens permitidas, separadas por vírgula (SEG-03). `*` é recusado (a API usa credenciais). Sem a variável, só fora de produção valem as origens locais de desenvolvimento. **Implementado** |
| `ENV` | Não | `development` | `development`, `test` ou `production`. Em `production` ativa as travas de CORS, `SECRET_KEY` e `AUTO_CREATE_TABLES`, e bloqueia `resetar_banco.py` |
| `AUTO_CREATE_TABLES` | Não | desligado | Liga `create_all` no startup; só dev/teste. Habilitar com `ENV=production` impede o início. O schema de produção depende de migrações (Alembic, pendente) |
| `DATA_ENCRYPTION_KEY` | **Sim, sempre** | — | AES-256-GCM dos campos sensíveis e da assinatura em disco. Base64 de **exatamente 32 bytes**. Sem ela (ou inválida) a aplicação **não inicia**. Nunca reutilizar (8.1) |
| `INDEX_KEY` | **Sim, sempre** | — | HMAC-SHA256 do índice cego (`tecnico.cnpj_idx`). Base64 de 32 bytes, **diferente** das demais |
| `INTEGRITY_KEY` | **Sim, sempre** | — | HMAC-SHA256 do selo de integridade da visita. Base64 de 32 bytes, **diferente** das demais |
| `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT` | Não | **`false`** | Modo de transição da cifragem. Padrão `false`: valor sem o prefixo `enc1:` em coluna cifrada é **erro** (tratado como adulteração; senão quem gravasse um CPF em claro direto no banco seria aceito sem alarme). `true` aceita **ler** valor em claro e só deve ser usado, fora de produção, durante a migração (`cifrar_dados_existentes.py`). **Com `ENV=production`, `true` é recusado e a aplicação não inicia** |
| `SHA256_ORIGEM_OBRIGATORIO` | Não | **`true`** | `true` (padrão, decisão do responsável em 08/11/2026: o app ainda não foi distribuído) exige o campo `sha256` em **todo** upload (app e painel); `false` aceita sem ele (o servidor grava o hash que calculou) e só deve ser usado se houver app antigo, sem envio de hash, em uso. O servidor **sempre** calcula e grava o seu |
| `DB_SSLMODE` | Não | `require` | TLS até o PostgreSQL: `require`, `verify-ca` ou `verify-full`. `disable`/`allow`/`prefer` só fora de produção. Ignorado em SQLite |
| `DB_SSLROOTCERT` | Não | — | Caminho do certificado raiz do provedor (para `verify-ca`/`verify-full`) |
| `SUPABASE_URL` | Sim em produção; junto com a chave | — | URL do projeto Supabase (`https://...`). **Definir junto com `SUPABASE_SERVICE_KEY`** (uma sem a outra impede a inicialização). Sem as duas: disco local (só dev/teste; recusado em `ENV=production`) |
| `SUPABASE_SERVICE_KEY` | Sim em produção; junto com a URL | — | Chave de serviço (**ignora o RLS**). Só no backend: nunca em painel, app, log ou Git; trocar se vazar |
| `STORAGE_BUCKET` | Não | `fast-ariam-privado` | Bucket privado dos arquivos (`fast-ariam-privado-dev` fora de produção, pois dev e produção compartilham o projeto) |

> **Ambiente (decisão do PO, 07/11/2026, risco aceito):** nesta fase desenvolvimento e produção usam o **mesmo projeto Supabase**. Consequência: testes, `resetar_banco.py --allow-remote` e migrações de desenvolvimento podem atingir dados reais, o que enfraquece as travas SEG-05 e SEG-12. A ressalva de Segurança permanece registrada na seção 8 e o risco deve ser reavaliado antes do uso em produção plena.

Variável do painel: `VITE_API_URL` (vazia usa o proxy do Vite para `127.0.0.1:8000`).
Variável do app: hoje a URL está fixa no código (`10.0.2.2:8000`). **[DIVERGÊNCIA PR-14]** O app é distribuído **somente para Android**.

## 3. Papéis e matriz de permissões

Papéis: `admin` e `tecnico` (enum `UserRole`).

| Ação | admin | tecnico (própria OS) | tecnico (outra OS) |
|---|:---:|:---:|:---:|
| Login | ✅ | ✅ | ✅ |
| Trocar a própria senha | ✅ | ✅ | ✅ |
| CRUD de técnicos (listar, criar, editar, desativar) | ✅ | ❌ | ❌ |
| Alterar dados bancários do técnico | ✅ | ❌ | ❌ |
| Criar, editar e desativar cliente | ✅ | ❌ | ❌ |
| Ler cliente por id | ✅ | ✅ (apenas clientes das próprias OS) | ❌ 403 (SEG-11, implementado) |
| Criar OS | ✅ | ❌ | ❌ |
| Listar OS | ✅ (todas) | ✅ (só as suas) | — |
| Ler OS | ✅ | ✅ | ❌ |
| Atribuir técnico (`PATCH` com `id_tecnico_atribuido`); o destino deve ser usuário ativo com papel `tecnico` (administrador não recebe OS) | ✅ | ❌ | ❌ |
| Alterar status da OS (`PATCH` com `status`) | O status não é livre: só é aceito o valor igual à transição implícita da atribuição (`Pendente` → `Agendado`); `Finalizado` → 403; qualquer outro → 409 | ❌ 403 sempre no `PATCH` da OS; usa os endpoints de ação da visita | ❌ |
| Cancelar OS (`POST .../cancelar`, com motivo) | ✅ | ❌ | ❌ |
| Criar visita | ✅ | ✅ | ❌ |
| Editar visita (`PATCH`) | ✅ | ✅ | ❌ |
| Iniciar e finalizar deslocamento | ❌ | ✅ | ❌ |
| Upload de foto de deslocamento | ✅ | ✅ | ❌ |
| Iniciar atendimento | ❌ | ✅ | ❌ |
| Pausar OS | ✅ **[DIVERGÊNCIA PR-08: hoje a rota exige técnico]** | ✅ | ❌ |
| Reagendar OS | ✅ | ❌ | ❌ |
| Registrar defeito, materiais, fotos e conserto sobre o equipamento **já vinculado** à OS (nunca cria equipamento) | ❌ | ✅ | ❌ |
| Gerenciar catálogo de modelos de equipamento (criar, editar, desativar) *(v0.5)* | ✅ | ❌ | ❌ |
| Vincular, corrigir e remover equipamento (modelo + série) da OS *(v0.5; RN-45)* | ✅ | ❌ 403 | ❌ |
| Ler os equipamentos da OS *(v0.5)* | ✅ | ✅ (somente leitura, própria OS) | ❌ 403 |
| Corrigir fotos comprobatórias e materiais de OS **Finalizada** *(v0.5; RN-49, 6.13)* | ✅ (auditado) | ❌ 403 | ❌ |
| Finalizar atendimento com assinatura | ❌ | ✅ | ❌ |
| Concluir OS manualmente | — | — | — |
| Ver custos da OS | ✅ | ✅ | ❌ |
| Alterar configuração global de custo por interface de técnico | ❌ | ❌ | — |
| Consultar custo calculado da OS | ✅ | ✅ (própria OS) | ❌ |

> **Decisão de contrato:** não existe "concluir OS" manual. A OS conclui ao finalizar o deslocamento de volta de uma visita sem pausa ativa (PRD RF-14). `POST /concluir` foi removido e `PATCH` com status `Finalizado` é recusado com 403 (PR-04, implementado).

> **Regra de atribuição (v0.4):** só o papel `tecnico` é atribuível a OS. O administrador não recebe OS, nem na criação nem por `PATCH`; a API recusa com 400 (código atual). Por isso desativar um administrador não desatribui nada.

## 4. Modelo de dados

Tabelas e colunas conforme os modelos SQLAlchemy (`backend/app/models`). Chaves estrangeiras indicadas com `→`.

### 4.1 `tecnico`

| Coluna | Tipo | Restrição |
|---|---|---|
| id_tecnico | INTEGER | PK, autoincrement |
| nome | VARCHAR(100) | NOT NULL |
| cnpj | **TEXT (cifrado, v0.6)** | NOT NULL. Máscara canônica `00.000.000/0000-00` **antes de cifrar**. Sem UNIQUE: a unicidade é de `cnpj_idx` |
| cnpj_idx | VARCHAR(64) | NOT NULL, UNIQUE (`uq_tecnico_cnpj_idx`). **Índice cego** `HMAC-SHA256(INDEX_KEY, "tecnico.cnpj\|<14 dígitos>")` em hex; ignora a máscara. Mantido automaticamente pelo model (v0.6) |
| cpf | **TEXT (cifrado, v0.6)** | NOT NULL. Máscara canônica `000.000.000-00` (14 caracteres) **antes de cifrar** |
| inscricao_estadual | VARCHAR(50) | |
| email | VARCHAR(100) | NOT NULL, UNIQUE |
| telefone | **TEXT (cifrado, v0.6)** | |
| password_hash | VARCHAR(100) | NOT NULL |
| role | ENUM(admin, tecnico) | NOT NULL, default `tecnico` |
| is_active | BOOLEAN | NOT NULL, default true |
| banco, agencia, conta | **TEXT (cifrados, v0.6)** | |
| pix | **TEXT (cifrado, v0.6)** | |

> **v0.6:** colunas marcadas "cifrado" guardam `enc1:<base64>` (8.1); a API continua recebendo e devolvendo o valor em claro (decifrado pelo tipo `TextoCifrado`). O e-mail permanece em claro (chave de login).

### 4.2 `cliente`

| Coluna | Tipo | Restrição |
|---|---|---|
| id_cliente | INTEGER | PK |
| razao_social | VARCHAR(100) | NOT NULL |
| codigo | INTEGER | NOT NULL, UNIQUE |
| contato_principal_nome | VARCHAR(100) | |
| contato_principal_telefone | VARCHAR(20) | |
| telefone | VARCHAR(20) | |
| endereco, numero, bairro, cidade | VARCHAR(200 / 20 / 100 / 100) | |
| uf | VARCHAR(2) | NOT NULL |
| is_active | BOOLEAN | NOT NULL, default true |

### 4.3 `ordem_servico`

| Coluna | Tipo | Restrição |
|---|---|---|
| id_os | INTEGER | PK |
| id_cliente | INTEGER | NOT NULL → `cliente` |
| id_tecnico_atribuido | INTEGER | → `tecnico`, pode ser NULL |
| status | ENUM(StatusChamado) | NOT NULL, DEFAULT `Pendente`; o serviço de criação define explicitamente `Agendado` quando a OS nasce com técnico ativo |
| is_cancelled | BOOLEAN | NOT NULL, default false |
| data_abertura | DATE | NOT NULL |
| data_agendamento | DATE | |
| data_conclusao | DATE | |
| descricao_cliente | TEXT | |
| pedido | VARCHAR(100) | |
| data_faturamento | DATE | |
| em_garantia | BOOLEAN | NOT NULL, default true |
| assinatura_cliente_url | VARCHAR(255) | |

**Enum `StatusChamado` (valores de negócio v0.3):** `Pendente`, `Agendado`, `Em Atendimento`, `Pausado`, `Aguardando Reagendamento`, `Finalizado`. `Aberto` pode permanecer temporariamente no banco apenas durante a migração de legado; nenhuma nova operação pode gravá-lo.

### 4.4 `visita`

| Coluna | Tipo | Observação |
|---|---|---|
| id_visita | INTEGER | PK |
| id_os | INTEGER | NOT NULL → `ordem_servico` |
| data_visita | DATE | NOT NULL |
| hora_inicio_deslocamento, hora_chegada_cliente, hora_inicio_atendimento, hora_fim_atendimento | VARCHAR(5) | Formato `HH:mm`. Legado, pouco usado |
| km_total | INTEGER | NOT NULL, default 0 |
| km_inicio_ida, km_fim_ida, km_inicio_volta, km_fim_volta | INTEGER | |
| hora_inicio_ida, hora_fim_ida, hora_inicio_volta, hora_fim_volta | VARCHAR(5) | `HH:mm` |
| hora_inicio_atendimento, hora_fim_atendimento | VARCHAR(5) | Atendimento, usado pelo estado |
| valor_pedagio, valor_frete_devolucao | NUMERIC(10,2) | NOT NULL, default 0 |
| descricao_servico_executado | TEXT | |
| nome_ajudante | VARCHAR(100) | Campo legado; fora do escopo v0.3, manter temporariamente apenas para histórico/migração |
| telefone_ajudante | VARCHAR(20) | Campo legado; fora do escopo v0.3, manter temporariamente apenas para histórico/migração |
| servico_finalizado | BOOLEAN | NOT NULL, default false |
| pendencia | TEXT | |
| odometro_inicio_url, odometro_fim_url | VARCHAR(255) | |
| foto_inicio_ida_url, foto_fim_ida_url, foto_inicio_volta_url, foto_fim_volta_url | VARCHAR(255) | |
| documento_cliente | **TEXT (cifrado, v0.6)** | CPF do cliente (11 dígitos **antes de cifrar**, validado no backend). O `CHECK ck_visita_documento_cliente` foi **removido** (não se aplica a texto cifrado) |
| assinatura_url | VARCHAR(255) | Referência `/static/assinaturas/<uuid>.enc`: **identificador, não URL pública** (a rota não existe); a imagem sai por `GET .../assinatura` (6.6) |
| assinatura_sha256 | VARCHAR(64) | *(v0.6)* SHA-256 dos bytes da assinatura **antes de cifrar**. `CHECK` 64 hex minúsculos |
| arquivos_sha256 | JSONB | *(v0.6, D2)* `{campo_url: sha256}` das fotos de odômetro/deslocamento (`foto_*_url`, `odometro_*_url`) |
| selo_integridade | VARCHAR(64) | *(v0.6, D1)* `HMAC-SHA256(INTEGRITY_KEY, JSON canônico)` em hex. NULL = visita sem selo (finalizada antes da v0.6 ou ainda aberta) |
| selo_versao | INTEGER | *(v0.6)* Versão do esquema canônico do selo (hoje `1`) |

### 4.5 `servico_equipamento`, `servico_defeito`, `servico_foto`, `material`

| Tabela | Colunas principais | Observação |
|---|---|---|
| servico_equipamento | id_servico PK, id_visita → visita, **id_os_equipamento → os_equipamento (RESTRICT)** *(v0.5)*, **conserto_salvo_em TIMESTAMPTZ** *(v0.5; preenchido só por "Salvar conserto")*, **is_legado BOOLEAN NOT NULL** *(v0.5)*, numero_serie_atendido VARCHAR(100) *(legado; era NOT NULL)*, nome_equipamento VARCHAR(100) *(legado)*, defeito_outros_descricao TEXT, vazamento_ponto_descricao TEXT | **v0.5:** um registro por equipamento da OS **em cada visita**, criado pelo servidor (6.5.3). `numero_serie_atendido` e `nome_equipamento` são legado, somente leitura, e não são aceitos de nenhum cliente; modelo e série exibidos vêm do vínculo. `UNIQUE(id_visita, id_os_equipamento)`; `CHECK (is_legado OR id_os_equipamento IS NOT NULL)` |
| servico_defeito | id_defeito PK, id_servico → servico_equipamento (CASCADE), tipo VARCHAR(50), defeito VARCHAR(100) | `tipo` ∈ principal, refrigeracao, compressor, vazamento, outros, iluminacao, estrutura |
| servico_foto | id_foto PK, id_servico → servico_equipamento (CASCADE), tipo VARCHAR(20), url VARCHAR(255), **sha256 VARCHAR(64)** *(v0.6)* | `tipo` ∈ defeito, conserto. `sha256` = hash dos bytes recebidos, calculado pelo servidor |
| material | id_material PK, id_servico → servico_equipamento, nome VARCHAR(100), quantidade INTEGER, valor NUMERIC(10,2) | |

### 4.6 `comprovante` e `pausa`

| Tabela | Colunas principais | Observação |
|---|---|---|
| comprovante | id_comprovante PK, id_visita → visita (CASCADE), tipo VARCHAR(50), url VARCHAR(255), **sha256 VARCHAR(64)** *(v0.6)* | `tipo` ∈ pedagio, frete |
| pausa | id_pausa PK, visita_id → visita, motivo VARCHAR(100) NOT NULL, descricao TEXT, criado_em TIMESTAMPTZ, por_tecnico_id → tecnico, is_ativa BOOLEAN NOT NULL default true | Pausa ativa é `is_ativa = true` |

**Relações:** cliente 1—N ordem_servico · tecnico 1—N ordem_servico · ordem_servico 1—N visita · **ordem_servico 1—N os_equipamento N—1 equipamento_modelo** *(v0.5)* · visita 1—N servico_equipamento **N—1 os_equipamento** *(v0.5)* · servico_equipamento 1—N (material, servico_defeito, servico_foto) · visita 1—N (comprovante, pausa).

### 4.7 Alterações de modelo da v0.3

**`ordem_servico` (alterar)**

| Coluna | Tipo | Observação |
|---|---|---|
| motivo_cancelamento | TEXT | Obrigatório quando `is_cancelled = true` |
| cancelado_em | TIMESTAMPTZ | |
| cancelado_por | INTEGER → `tecnico` | Id do administrador |
| assinatura_cliente_url | VARCHAR(255) | **Descontinuada.** A assinatura passa para a visita (PR-35). Manter só para dados antigos |

**`visita` (alterar)**

| Coluna | Tipo | Observação |
|---|---|---|
| assinatura_url | VARCHAR(255) | Caminho no Storage |
| nome_cliente_assinatura | VARCHAR(100) | Quem assinou (PR-10) |
| documento_cliente | VARCHAR(11) | CPF **do cliente**, só dígitos (11), validado. Diferente do CPF do técnico (14, mascarado) |
| ida_inicio_em, ida_fim_em | TIMESTAMPTZ | Momento real da ação, vindo do aparelho |
| atendimento_inicio_em, atendimento_fim_em | TIMESTAMPTZ | Idem |
| volta_inicio_em, volta_fim_em | TIMESTAMPTZ | Idem |

As colunas `hora_*` em `HH:mm` ficam como legado, derivadas dos novos campos (no fuso `America/Sao_Paulo`), até os fronts migrarem. Na v0.4 `assinatura_url`, `nome_cliente_assinatura`, `documento_cliente` e os seis `*_em` (gravados em UTC) fazem parte do contrato de resposta da visita (6.6.5). O `km_total` passa a ser calculado por fórmula confirmada: (`km_fim_ida` − `km_inicio_ida`) + (`km_fim_volta` − `km_inicio_volta`).

**`pausa` (alterar)**

| Coluna | Tipo | Observação |
|---|---|---|
| por_usuario_id | INTEGER → `tecnico` | Substitui `por_tecnico_id`. Pode ser admin |
| por_papel | VARCHAR(10) | `admin` ou `tecnico` |
| motivo | VARCHAR(100) | Um dos 5 valores oficiais (seção 7) |
| encerrada_em | TIMESTAMPTZ | Preenchido quando `is_ativa` vira false |

**Novas tabelas**

| Tabela | Colunas principais | Finalidade |
|---|---|---|
| configuracao_custo | id_configuracao SMALLINT PK (linha única), primeira_hora_tecnico NUMERIC(10,2), hora_tecnico NUMERIC(10,2), tempo_deslocamento_tecnico NUMERIC(10,2), quilometragem NUMERIC(10,2), atualizado_em TIMESTAMPTZ | Configuração global do sistema; sem FK para técnico, sem edição pelo app do técnico |
| custo_os | id_os PK/FK, calculado_em TIMESTAMPTZ, total NUMERIC(12,2), detalhes JSONB, valores_utilizados JSONB | Snapshot obrigatório do cálculo e dos valores globais na finalização |
| sync_evento | client_event_id UUID PK, id_tecnico FK, id_os FK, id_visita FK, tipo VARCHAR(50), ocorrido_em TIMESTAMPTZ, recebido_em TIMESTAMPTZ, payload JSONB, resultado VARCHAR(12), codigo VARCHAR(40), detalhe TEXT | Idempotência e rastreio da sincronização (6.12) |
| log_acao | id PK, id_os, id_usuario, papel, acao, criado_em, payload JSONB | Auditoria (PR-20) |

**Ajustes de restrição**

- `cliente.codigo`: continua NOT NULL e UNIQUE. O schema passa a exigi-lo (PR-27).
- `ordem_servico.id_tecnico_atribuido`: continua anulável. Deve ser NULL para `Pendente`. É removido em conflitos administrativos offline que movam a OS para `Pendente` e na desativação do técnico (RN-08a, resolvida: desatribuição em massa das OS não finalizadas e não canceladas). Só usuários com papel `tecnico` podem ser referenciados (administrador não recebe OS).
- `servico_foto.tipo`: restrição CHECK em (`defeito`, `conserto`).
- `comprovante.tipo`: restrição CHECK em (`pedagio`, `frete`).

**Migrações:** não existem. O schema é criado por `Base.metadata.create_all`. **[DIVERGÊNCIA PR-19]** Antes da próxima mudança de modelo, adotar Alembic.

### 4.8 `equipamento_modelo` e `os_equipamento` (novas, v0.5)

**Migração aplicada no Supabase real em 08/11/2026** (`backend/migrations/0007_equipamento_os.sql`, via MCP em 5 partes; a OS existente era `Finalizado` e sem serviços: nada a migrar; modelos SQLAlchemy com os mesmos nomes de constraints e índices). Estilo idempotente das migrações existentes (`backend/migrations/`).

**`equipamento_modelo`** (catálogo; só o modelo)

| Coluna | Tipo | Restrição |
|---|---|---|
| id_equipamento_modelo | INTEGER | PK, identity |
| modelo | VARCHAR(100) | NOT NULL, sem espaços nas pontas e não vazio (CHECK). **UNIQUE sem diferenciar maiúsculas** (índice único em `lower(modelo)`) |
| is_active | BOOLEAN | NOT NULL, default true |
| criado_em | TIMESTAMPTZ | NOT NULL, default now() |

**`os_equipamento`** (vínculo da OS)

| Coluna | Tipo | Restrição |
|---|---|---|
| id_os_equipamento | INTEGER | PK, identity |
| id_os | INTEGER | NOT NULL → `ordem_servico` (**RESTRICT**) |
| id_equipamento_modelo | INTEGER | NOT NULL → `equipamento_modelo` (**RESTRICT**) |
| numero_serie | VARCHAR(100) | NOT NULL, sem espaços nas pontas e não vazio (CHECK). **UNIQUE por OS sem diferenciar maiúsculas** (índice único em `(id_os, upper(numero_serie))`) |
| origem | VARCHAR(20) | NOT NULL, default `admin`; CHECK ∈ (`admin`, `backfill_legado`) |
| criado_em | TIMESTAMPTZ | NOT NULL, default now() |

Índice adicional: `os_equipamento (id_equipamento_modelo)`. O serviço normaliza a série (trim; comparação sem diferenciar maiúsculas) e o modelo (trim) antes de gravar.

**Regras de integridade**

- Não existe `DELETE` de modelo: o `RESTRICT` impede e o domínio usa desativação lógica (`is_active = false`, que só bloqueia **novos** vínculos — regra de serviço, não FK). O `ON DELETE CASCADE` já existente em defeito/foto/comprovante **não** é estendido a estas tabelas.
- Remover `os_equipamento` é regra de serviço (6.13): bloqueado se houver conteúdo registrado (foto, defeito, material ou conserto salvo) em qualquer visita; registros de serviço **vazios** criados automaticamente são removidos na mesma transação.
- *(Recomendado)* **Trigger de consistência** em `servico_equipamento` (BEFORE INSERT/UPDATE, `SET search_path = public`): recusa `id_os_equipamento` cujo `id_os` difere do `id_os` da visita (uma FK simples não garante isso). Erro 23514.
- *(Recomendado)* **Backstop de estado** em `visita`: CHECKs de linha única (`atendimento_fim_em IS NULL OR atendimento_inicio_em IS NOT NULL`; fim ≥ início) e trigger BEFORE UPDATE disparado só na transição `NULL → NOT NULL` de `atendimento_inicio_em`/`atendimento_fim_em`, que repete as consultas das regras 6 e 7. Disparar só na transição evita invalidar legado. **A autoridade continua sendo o serviço** (AR-09).
- **RLS/SEG-12:** `ENABLE ROW LEVEL SECURITY` (sem políticas) e `REVOKE ALL ... FROM anon, authenticated` nas duas tabelas e nas suas sequences; rodar `get_advisors` do Supabase depois. A API conecta como dono. Ver SEG-20.

**Consulta de apoio (pendências de foto de defeito na visita)**; a de conserto é análoga, com `tipo = 'conserto'` e `conserto_salvo_em IS NOT NULL`:

```sql
SELECT oe.id_os_equipamento
FROM visita v
JOIN os_equipamento oe ON oe.id_os = v.id_os
WHERE v.id_visita = :v
  AND NOT EXISTS (SELECT 1 FROM servico_equipamento se
                  JOIN servico_foto f ON f.id_servico = se.id_servico AND f.tipo = 'defeito'
                  WHERE se.id_visita = v.id_visita
                    AND se.id_os_equipamento = oe.id_os_equipamento);
```

O índice `servico_foto (id_servico, tipo)` só deve ser criado após `EXPLAIN` com volume real.

### 4.9 Migração de dados legados (v0.5)

**Não implementada.** Entregar como `.sql` numerado e idempotente no padrão do `0001` (próximo número livre em 08/11/2026: **0007**; conferir a pasta), com `BEGIN/COMMIT` e `lock_timeout`, e script de rollback. Não usar `create_all`. Como dev e produção compartilham o mesmo projeto Supabase (risco aceito, seção 2), **a execução real é em produção**: ensaiar antes em dump restaurado em PostgreSQL local, em janela de baixo uso.

Fases (expandir → backfill → backend compatível com os dois modos → contrair):

1. **Backup:** `pg_dump` de `ordem_servico`, `visita`, `servico_*`, `material`, `pausa`, guardado fora do Supabase (o plano Free pode não ter backup automático: confirmar).
2. **Inventário (somente leitura):** `GROUP BY` de `nome_equipamento` e `upper(btrim(numero_serie_atendido))`; séries repetidas na mesma OS/visita; mesma série com nomes diferentes na mesma OS; nome nulo ou vazio; OS em andamento (Agendado, Em Atendimento, Pausado) sem equipamento.
3. **Expansão (DDL):** cria as tabelas de 4.8; em `servico_equipamento` adiciona `id_os_equipamento`, `conserto_salvo_em` e `is_legado BOOLEAN NOT NULL DEFAULT true` (o **default true** na expansão é obrigatório: o backend antigo continua inserindo serviços sem vínculo; um default false derrubaria o `CHECK`), remove `NOT NULL` de `numero_serie_atendido` e acrescenta `CHECK (is_legado OR id_os_equipamento IS NOT NULL)`, `CHECK (id_os_equipamento IS NOT NULL OR numero_serie_atendido IS NOT NULL)` e `UNIQUE (id_visita, id_os_equipamento)` (aceita vários `NULL` do legado). Cada `ADD CONSTRAINT` com guarda `IF NOT EXISTS` em bloco `DO`.
4. **Semear o catálogo** com `DISTINCT btrim(nome_equipamento)` (`ON CONFLICT DO NOTHING`), gerando relatório para o administrador mesclar variantes ("Freezer" / "freezer vert."). Não inventar modelo para quem não tem nome (proposta: modelo "Não catalogado", a revisar).
5. **Backfill de `os_equipamento`** com `origem = 'backfill_legado'` a partir de `servico_equipamento` JOIN `visita` (série com trim; modelo casado por `lower`), `ON CONFLICT DO NOTHING` no índice `(id_os, upper(serie))`. Várias visitas da mesma OS com a mesma série geram **um** `os_equipamento` e vários serviços.
6. **Backfill do vínculo:** preenche `id_os_equipamento` e `is_legado = false` somente onde `id_os_equipamento IS NULL`. Serviços legados que já têm fotos podem ter `conserto_salvo_em` preenchido pela data da visita finalizada (proposta; decidir no inventário).
7. **Exceções** (serviço sem nome de modelo, duplicata na mesma visita, série conflitante) permanecem `is_legado = true` com `numero_serie_atendido` preservado e vão para o relatório.
8. **Contração (migração posterior, após aceite do PO):** troca o default de `is_legado` para `false`. **Não** aplicar `NOT NULL` em `id_os_equipamento` (o CHECK já cobre) e **nunca** remover `nome_equipamento` nem `numero_serie_atendido` (histórico).

**OS legadas sem equipamento:** não impor mínimo de 1 no banco (a OS legada violaria a restrição); o mínimo é regra da API: criação sem equipamento é recusada (RN-41) e a OS legada não finalizada sem equipamento fica **sem poder ser atribuída, reagendada nem iniciada** até o admin vincular (RN-46, TR-15); **completar essas OS antes de ligar o novo app** (risco operacional: OS "Em Atendimento" sem equipamento travam o técnico, que não cadastra mais). OS Finalizadas, assinaturas e custo congelado permanecem idênticos (conferir contagens e checksums antes/depois). Zero fotos órfãs. Idempotência: cada passo usa `IF NOT EXISTS`, `ON CONFLICT` ou `WHERE ... IS NULL`.

**Rollback:** a fase aditiva é reversível (`UPDATE ... SET id_os_equipamento = NULL, is_legado = true`; apagar só `origem = 'backfill_legado'`; dropar colunas e tabelas) com o backend antigo no ar. Dados criados após o go-live se perdem no rollback: depois do go-live preferir *roll-forward*. Quando o Alembic entrar (PR-19), fazer o baseline/stamp incluindo estes objetos com os mesmos nomes dos models. **Nada disto foi testado em PostgreSQL.**

## 5. Máquina de estados da OS

### 5.1 Estados e gatilhos

| De | Para | Gatilho (endpoint) | Quem | Regras |
|---|---|---|---|---|
| (criação sem técnico) | Pendente | `POST /api/chamados/` sem `id_tecnico_atribuido` | admin/sistema | OS não finalizada e sem técnico |
| (criação com técnico) | Agendado | `POST /api/chamados/` com técnico | admin | Técnico ativo com papel `tecnico`; RN-10. Cria a visita aberta na mesma transação (RN-11a, 6.5.3) |
| Pendente | Agendado | `PATCH /api/chamados/{id}` com `id_tecnico_atribuido` | admin | Técnico ativo com papel `tecnico`; atribuição obrigatória. Cria a visita aberta na mesma transação (RN-11a, 6.5.3). **v0.5: a OS precisa ter ao menos um equipamento (TR-15); OS legada sem equipamento → 409** |
| Agendado | Em Atendimento | `POST .../visitas/{v}/iniciar-atendimento` | técnico atribuído | Ida finalizada antes do atendimento. **v0.5: a OS tem ao menos um equipamento e cada equipamento tem ≥ 1 foto de defeito na visita (TR-12); caso contrário 409** |
| Em Atendimento | Pausado | `POST .../visitas/{v}/pausar` | técnico ou admin | Visita em atendimento e não finalizada; RN-26, RN-29, RN-30 |
| Em Atendimento | Finalizado | `POST .../finalizar-deslocamento` com `tipo=volta` e sem pausa ativa | técnico | Atendimento encerrado e validações de odômetro/comprovantes cumpridas |
| Pausado | Aguardando Reagendamento | `POST .../finalizar-deslocamento` com `tipo=volta` e pausa ativa | técnico | Finaliza visita; não permite reagendamento antes da volta |
| Aguardando Reagendamento | Agendado | `POST /api/chamados/{id}/reagendar` | admin | Cria nova visita, encerra pausa |
| Agendado (ida não iniciada) | Agendado | `POST /api/chamados/{id}/reagendar` | admin | Atualiza data da visita existente |
| OS não finalizada em conflito de sincronização | Pendente | processamento de `POST /api/sync/eventos` | sistema | Rejeita eventos conflitantes, remove atribuição e audita o conflito |
| Qualquer status, exceto Finalizado/já cancelado | `is_cancelled = true` | `POST /api/chamados/{id}/cancelar` | admin | Motivo obrigatório; encerra pausas ativas |
| Técnico desativado | Pendente | `DELETE /api/tecnicos/{id}` | admin/sistema | Desatribui **todas** as OS do técnico não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) na mesma transação; histórico preservado; ação auditada em `log_acao` (RN-08a, v0.4) |

**Visita automática (RN-11a):** toda entrada em `Agendado` (criação com técnico, atribuição a `Pendente`, reagendamento) garante uma visita aberta na mesma transação, com `data_visita` = `data_agendamento` ou, se vazia, a data de hoje em `America/Sao_Paulo`. Após a desativação do técnico (RN-08a), a visita iniciada pelo técnico anterior permanece como histórico e a reatribuição cria uma visita nova para o novo técnico.

`Aberto` é legado e não será produzido pela API após a migração. `Pendente` passa a significar exclusivamente OS não finalizada sem técnico atribuído. O cancelamento continua sendo uma flag lógica, não um valor de enum.

### 5.2 Diagrama

```text
                    atribuir técnico (admin)
 (criação sem técnico) ──► [Pendente] ───────────────► [Agendado]
                                                         │
                                                         │ iniciar atendimento
                                                         ▼
                                                   [Em Atendimento]
                                                     │          │
                                           pausar    │          │ volta sem pausa
                                                     ▼          ▼
                                                  [Pausado] [Finalizado]
                                                     │
                                            finalizar volta
                                                     ▼
                                           [Aguardando Reagendamento]
                                                     │ reagendar (admin)
                                                     ▼
                                                  [Agendado]

 conflito offline incompatível ──► [Pendente] + sem técnico + auditoria
 cancelamento: is_cancelled=true (flag, não é status)
```

### 5.3 Regras de transição

- **TR-01** Só são permitidas as transições da tabela 5.1. Qualquer outra resposta é HTTP 409 com `detail` explicando a transição.
- **TR-02** A transição para `Finalizado` só pode acontecer ao finalizar o deslocamento de volta de uma visita sem pausa ativa. Nenhum papel finaliza por `PATCH` ou endpoint próprio.
- **TR-03** `Pausado` não pode ir para `Em Atendimento` por `PATCH`; não existe retomada no fluxo aprovado.
- **TR-04** Reagendar só é permitido a partir de `Aguardando Reagendamento` ou `Agendado` com ida ainda não iniciada. `Pausado`, `Pendente`, `Em Atendimento`, `Finalizado` e canceladas retornam 409.
- **TR-05** Finalizar a volta de visita com pausa ativa leva a OS a `Aguardando Reagendamento`. Somente depois dessa transição o administrador pode criar a próxima visita.
- **TR-06** Desativar um técnico desatribui automaticamente todas as suas OS não finalizadas e não canceladas (qualquer status), que passam para `Pendente`, nunca `Aberto`, preservando visitas, fotos, serviços e pausas e auditando em `log_acao` (RN-08a). OS Finalizadas e canceladas não mudam.
- **TR-07** Eventos offline passam pelas mesmas regras do fluxo online, com controle temporal e idempotência. Em conflito administrativo incompatível, aplicar SY-05 e mover a OS não finalizada para `Pendente`, sem técnico.
- **TR-08** `Pendente` deve sempre ter `id_tecnico_atribuido IS NULL`; `Agendado`, `Em Atendimento`, `Pausado` e `Aguardando Reagendamento` devem manter atribuição ativa, exceto durante transação de reconciliação devidamente controlada.
- **TR-09** `Aberto` é valor legado. Nenhuma nova escrita pode persistir esse valor após a migração de status.
- **TR-10** Toda OS que entra em `Agendado` possui, ao final da mesma transação, uma visita aberta (RN-11a). `POST /api/chamados/{id}/visitas` retorna 409 se já existir visita não finalizada.
- **TR-11** Só usuário ativo com papel `tecnico` pode ser `id_tecnico_atribuido`; o administrador não recebe OS.
- **TR-12** *(v0.5)* `iniciar-atendimento` exige, na mesma transação e **depois** das checagens existentes (visita vigente, atendimento já iniciado, ida finalizada, OS `Agendado`): (a) a OS tem ao menos um `os_equipamento` (RN-46) e (b) todo `os_equipamento` da OS tem ≥ 1 `servico_foto(tipo = 'defeito')` em `servico_equipamento` **da visita atual**. Falha → 409 com o `detail` listando os pendentes (modelo e série). A validação fica no serviço (há dois caminhos de início: rota da OS e rota da visita) e é reaplicada aos eventos de sincronização.
- **TR-13** *(v0.5)* `finalizar-atendimento` exige, **depois** das checagens existentes (pausa ativa → 400, atendimento não iniciado, já finalizado, CPF → 422, assinatura) e **antes de gravar a assinatura**: todo `os_equipamento` da OS tem `servico_equipamento` na visita com `conserto_salvo_em` preenchido **e** ≥ 1 `servico_foto(tipo = 'conserto')`. Falha → 409 com pendências. Nada é gravado em caso de falha (nem nome, CPF ou assinatura).
- **TR-14** *(v0.5)* `finalizar-deslocamento` (`tipo = volta`) **não repete** TR-12/TR-13. Com atendimento finalizado, elas já foram verificadas; com pausa ativa a volta é permitida sem conserto (PRD RN-48). `PATCH` da visita não contorna as travas (continua recusando `servico_finalizado = true` fora do fluxo, 400).
- **TR-15** *(v0.5)* Toda OS tem ao menos um `os_equipamento`. A criação sem equipamento é recusada (422) e não se remove o último (409). OS **legada** sem equipamento é exceção transitória: atribuir técnico (`Pendente → Agendado`), reagendar e iniciar atendimento retornam 409 com a mensagem "OS sem equipamento vinculado" até o admin vincular (RN-46).

## 6. Contrato da API

Base: `/api`. Autenticação: `Authorization: Bearer <token>`. Erros seguem o padrão do FastAPI: `{"detail": "mensagem"}`. Erro de validação de corpo: HTTP 422 com lista de campos.

### 6.1 Códigos de resposta padronizados

| Código | Quando |
|---|---|
| 200 / 201 / 204 | Sucesso (201 em criação, 204 sem corpo) |
| 400 | Regra de negócio violada (ex.: odômetro obrigatório) |
| 401 | Token ausente, inválido ou expirado |
| 403 | Papel sem permissão ou OS de outro técnico |
| 404 | Recurso não encontrado ou cancelado |
| 409 | Transição de estado inválida ou conflito de estado (TR-01), por exemplo visita já aberta, OS Finalizada recebendo arquivo, reagendar sem técnico ativo. **Implementado.** *(v0.5, não implementado)* Também: iniciar atendimento sem foto de defeito (TR-12), finalizar sem conserto salvo/foto de conserto (TR-13), série duplicada na OS, alterar equipamento após o início do atendimento, remover equipamento com conteúdo ou o último da OS, modelo duplicado. As duas travas usam 409 (conflito resolvível pelo técnico) em vez de 400 (que fica para regra de negócio como a ida não finalizada); alternativa aceitável é 400 por coerência com RN-17 |
| 410 | Endpoint descontinuado (`finalizar-dados`) |
| 413 | Imagem acima de 15 MB |
| 422 | Corpo ou parâmetro inválido (validação Pydantic), inclusive `ocorrido_em` sem fuso ou mais de 5 minutos no futuro, data de reagendamento no passado e imagem que não é JPEG/PNG real |

### 6.2 Autenticação

| Método | Rota | Papel | Entrada | Saída |
|---|---|---|---|---|
| POST | `/api/auth/login` | público | `application/x-www-form-urlencoded`: `username` (e-mail), `password` | `{access_token, token_type: "bearer"}` |
| GET | `/api/auth/me` | autenticado | — | `{id_tecnico, nome, email, role, is_active}`. **Implementado (PR-06).** Nunca inclui dados bancários, CPF/CNPJ nem telefone (SEG-10) |

> **Natureza do JWT (v0.6):** o token é assinado com **HS256, um segredo simétrico compartilhado** (`SECRET_KEY`). Isso autentica o emissor para quem conhece o segredo; **não é assinatura assimétrica** (par chave pública/privada). Migrar para RS256/EdDSA exigiria proposta própria (`kid`, rotação, período de transição) e aprovação do PO; não foi feito. O certificado TLS autentica o **servidor**; o JWT autentica o **portador do token**; as senhas usam bcrypt. São controles distintos.

Claims do JWT: `sub` (e-mail), `user_id`, `role`, `exp`. A cada requisição o usuário é relido no banco: inexistente, inativo ou com e-mail diferente do `sub` recebe 401 com mensagem única, e o papel efetivo vem do banco, não do token (SEG-01, implementado).

### 6.3 Técnicos

| Método | Rota | Papel | Entrada | Saída |
|---|---|---|---|---|
| POST | `/api/tecnicos/` | admin | `TecnicoCreate` (ver 6.3.1) | 201 `Tecnico` |
| GET | `/api/tecnicos/?is_active=` | admin | — | `Tecnico[]` |
| GET | `/api/tecnicos/{id}` | admin | — | `Tecnico` |
| PATCH | `/api/tecnicos/{id}` | admin | `TecnicoUpdate` (parcial) | `Tecnico` |
| PATCH | `/api/tecnicos/me/password` | autenticado | `{old_password, new_password}` | 204 |
| DELETE | `/api/tecnicos/{id}` | admin | — | 204 (desativação lógica). Invalida as sessões existentes e, **na mesma transação**, desatribui todas as OS do técnico não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) → `Pendente`, sem técnico. Visitas, fotos, serviços e pausas são preservados (pausas ativas são encerradas: `is_ativa = false`, `encerrada_em`); OS Finalizadas e canceladas não mudam; uma linha `DESATRIBUIDA_POR_DESATIVACAO` por OS em `log_acao` (RN-08a, implementado) |

**6.3.1 `TecnicoCreate`**

```json
{
  "nome": "Eletropaulo Refrigeração",
  "cnpj": "00.000.000/0001-00",
  "cpf": "123.456.789-00",
  "inscricao_estadual": "ISENTO",
  "email": "tecnico@exemplo.com",
  "telefone": "(27) 99999-9999",
  "password": "senha-forte",
  "role": "tecnico",
  "is_active": true,
  "dados_bancarios": { "banco": "Banco X", "agencia": "0001", "conta": "12345-6", "pix": "tecnico@exemplo.com" }
}
```

Obrigatórios: `nome`, `cnpj`, `cpf`, `email`, `telefone`, `dados_bancarios` (com `banco`, `agencia`, `conta`), `password`.
**Formato de CPF e CNPJ (v0.4):** a API armazena e devolve o CPF com máscara canônica `000.000.000-00` (14 caracteres) e o CNPJ com `00.000.000/0000-00` (18 caracteres), mesmo que sejam enviados só com dígitos; a unicidade do CNPJ vale sobre a forma canônica. O CPF do **cliente** na assinatura é outro campo: só dígitos (11). A máscara exibida no painel é apenas visual (M3) e não substitui essa regra.
**Regra:** o painel **não deve** preencher telefone padrão quando o campo está vazio (ver PR-01 e PR-02).

### 6.4 Clientes

| Método | Rota | Papel | Entrada | Saída |
|---|---|---|---|---|
| POST | `/api/clientes/` | admin | `ClienteCreate` | 201 `Cliente` |
| GET | `/api/clientes/?is_active=` | admin | — | `Cliente[]` |
| GET | `/api/clientes/{id}` | autenticado | — | `Cliente` (técnico só dos clientes das próprias OS, SEG-11) |
| PATCH | `/api/clientes/{id}` | admin | `ClienteUpdate` (parcial) | `Cliente` |
| DELETE | `/api/clientes/{id}` | admin | — | 204 (desativação lógica) |

`ClienteCreate` obrigatórios: `razao_social`, `telefone`, `endereco`, `numero`, `bairro`, `cidade`, `uf` (2 caracteres). `codigo` (inteiro) **passa a ser obrigatório** no schema, digitado pelo administrador, e continua único no banco (PRD RN-04, PR-27).

### 6.5 Ordens de Serviço

| Método | Rota | Papel | Entrada | Saída | Regras |
|---|---|---|---|---|---|
| POST | `/api/chamados/` | admin | `ChamadoCreate` | 201 `Chamado` (com `equipamentos[]`) | Cliente ativo. Sem técnico → `Pendente`; com técnico ativo (papel `tecnico`) → `Agendado` e visita aberta criada na mesma transação (RN-11a). `status` enviado é ignorado. **v0.5: `equipamentos[]` obrigatório com ao menos 1 item (422 se vazio, ausente, com série repetida na lista, modelo inexistente ou inativo); os vínculos e os registros de serviço da visita são criados na mesma transação; falha em qualquer um desfaz tudo** |
| GET | `/api/chamados/?is_cancelled=` | autenticado | — | `Chamado[]` com `cliente_nome` | Técnico recebe só as próprias |
| GET | `/api/chamados/{id}` | autenticado | — | `Chamado` | 404 se cancelado. 403 se técnico não é o atribuído |
| PATCH | `/api/chamados/{id}` | admin | `ChamadoUpdate` (parcial) | `Chamado` | **Técnico: sempre 403.** Admin: campos administrativos e atribuição; `status` não é livre (só o valor igual à transição implícita; `Finalizado` → 403; outro → 409). `is_cancelled` e `data_conclusao` são recusados (400). Atribuir a `Pendente` cria a visita aberta (RN-11a) |
| POST | `/api/chamados/{id}/cancelar` | admin | `{motivo}` obrigatório | `Chamado` | RF-11, RN-12. Ver 6.9. Substitui o `DELETE /api/chamados/{id}`, **removido** (implementado, PR-28) |
| POST | `/api/chamados/{id}/concluir` | — | — | — | **Removido (implementado, PR-04).** A OS conclui na volta (RF-14) |
| GET | `/api/chamados/{id}/custos` | autenticado | — | `CustoTotalResponse` com `congelado`, `calculado_em` e `valores_utilizados` | Calcula com os valores globais do sistema; para OS finalizada, devolve o snapshot imutável gravado em `custo_os` com `congelado = true` (6.11) |
| POST | `/api/chamados/{id}/reagendar` | admin | `{data_visita}` (ou `VisitaCreate`) | 201 `Visita` (nova visita) ou 200 (data da visita existente alterada) | RN-14, TR-04, TR-05. Atualiza também `data_agendamento` da OS. Data passada → 422; exige técnico ativo → 409. Ver 6.10 |
| POST | `/api/chamados/{id}/visitas` | admin ou técnico atribuído | `VisitaCreate` | 201 `Visita` | `servico_finalizado` deve ser false. OS deve estar `Agendado`. **409 se já existe visita não finalizada** (a visita automática de RN-11a normalmente já existe) |
| POST | `/api/chamados/{id}/iniciar-atendimento` | técnico atribuído | — | `Chamado` | Somente status `Agendado`; `Pendente` não possui técnico e exige atribuição prévia |

**6.5.1 `ChamadoCreate`**

```json
{
  "id_cliente": 12,
  "descricao_cliente": "Gôndola sem refrigeração no setor de frios",
  "id_tecnico_atribuido": 3,
  "data_agendamento": "2026-11-03",
  "pedido": "PED-2026-0001",
  "em_garantia": true,
  "equipamentos": [
    { "id_equipamento_modelo": 4, "numero_serie": "FZ-88421" },
    { "id_equipamento_modelo": 4, "numero_serie": "FZ-88422" },
    { "id_equipamento_modelo": 7, "numero_serie": "FH-10031" }
  ]
}
```

`equipamentos` é **obrigatório (mín. 1)** na v0.5. `ChamadoUpdate` **não aceita** `equipamentos`: a manutenção do vínculo é pelo sub-recurso de 6.13, para que um `PATCH` não substitua a lista e quebre registros já feitos.

**6.5.2 `ChamadoUpdate` (admin, atribuir técnico) — exemplo correto**

```json
{ "id_tecnico_atribuido": 3 }
```

**6.5.3 Visita automática e destino de atribuição (v0.4)**

- Ao entrar em `Agendado` por criação com técnico, atribuição a `Pendente` ou reagendamento a partir de `Aguardando Reagendamento`, o serviço garante uma visita aberta (não finalizada) **na mesma transação** da mudança de status. Falha ao criar a visita desfaz toda a operação.
- `data_visita` = `data_agendamento` da OS; se vazia, a data de hoje em `America/Sao_Paulo` (e `data_agendamento` passa a refletir essa data).
- `id_tecnico_atribuido` só aceita usuário ativo com papel `tecnico`. Atribuir um administrador é recusado (400, código atual).
- Reatribuição depois da desativação do técnico anterior: a visita que o técnico anterior tenha iniciado fica como histórico; é criada visita nova para o novo técnico.
- **Registro de serviço por equipamento (v0.5):** a visita aberta nasce com **um `servico_equipamento` por `os_equipamento` da OS**, criado pelo servidor na mesma transação (inclusive nas visitas criadas por reatribuição e por reagendamento a partir de `Aguardando Reagendamento`). Se o administrador vincular novo equipamento enquanto a visita vigente estiver aberta e sem atendimento iniciado (RN-45), o registro correspondente é criado junto. O técnico nunca cria esse registro (`POST .../servicos` → 410, ver 6.7). OS legada sem equipamento (RN-46) não gera registros de serviço até o admin vincular.

> O painel envia `"status": "AGENDADO"` nesta chamada. **Isso gera 422**, porque o enum aceita "Agendado". Corrigir para `"Agendado"` ou omitir o campo (o backend já define Agendado ao atribuir). **[DIVERGÊNCIA PR-07]**

### 6.6 Visitas, deslocamento e atendimento

| Método | Rota | Papel | Entrada | Saída | Regras |
|---|---|---|---|---|---|
| PATCH | `/api/chamados/{id}/visitas/{v}` | técnico atribuído ou admin | `VisitaUpdate` (parcial) | `Visita` | Atualiza dados da visita e aplica validações; não finaliza a OS. A OS só finaliza no fim do deslocamento de volta sem pausa ativa |
| GET | `/api/chamados/{id}/visitas/{v}/estado` | autenticado | — | `EstadoVisita` (6.6.3) | Fonte de verdade para os botões do app |
| POST | `/api/chamados/{id}/visitas/{v}/iniciar-deslocamento` | técnico | `{tipo: "ida"|"volta", km_inicio: int, ocorrido_em?}` | `{message, tipo, km_inicio, hora_inicio}` | Ida: não pode repetir. Volta: exige fim do atendimento **ou** pausa ativa |
| POST | `/api/chamados/{id}/visitas/{v}/finalizar-deslocamento` | técnico | `{tipo, km_fim: int, ocorrido_em?}` | `Visita` | Exige início. Volta marca `servico_finalizado` e muda OS (ver 5.1) |
| POST | `/api/chamados/{id}/visitas/{v}/upload-deslocamento` | autenticado | multipart: `file`, `tipo` (ida/volta), `momento` (inicio/fim) | `Visita` | Grava na coluna `foto_{momento}_{tipo}_url` |
| POST | `/api/chamados/{id}/visitas/{v}/upload_file` | autenticado | multipart: `file`, `file_type` | `Visita` | `file_type` ∈ odometro_inicio_url, odometro_fim_url, foto_*_url (simples), comprovante_pedagio_urls, comprovante_frete_urls (listas) |
| POST | `/api/chamados/{id}/visitas/{v}/iniciar-atendimento` | técnico | `{ocorrido_em?}` (corpo opcional) | `Visita` | Grava `atendimento_inicio_em`. Muda OS para Em Atendimento. Exige o fim da ida (400) e OS `Agendado` (409) — implementado (RN-17, PR-36). **v0.5 (não implementado): exige ainda a OS com equipamento e ≥ 1 foto de defeito por equipamento na visita; senão 409 com a lista de pendentes (TR-12, RN-43)** |
| POST | `/api/chamados/{id}/visitas/{v}/pausar` | técnico ou admin | `{motivo: str, descricao?: str, ocorrido_em?}` | `{status, id_pausa, visita_id, motivo, descricao, criado_em, is_ativa}` | RN-26, RN-29, RN-30. Muda OS para Pausado. `motivo` = "Outro" exige `descricao` |
| POST | `/api/chamados/{id}/visitas/{v}/finalizar-atendimento` | técnico | `{nome_cliente, documento_cliente, assinatura_base64, assinatura_sha256?, ocorrido_em?}` | `{status, assinatura_url}` | RN-22, RN-23. `documento_cliente` é CPF válido. Grava assinatura, nome e CPF **na visita**, não na OS (PR-10, PR-35). **v0.5 (não implementado): antes de gravar a assinatura exige conserto salvo e ≥ 1 foto de conserto por equipamento da OS na visita; senão 409 com pendências e nada é gravado (TR-13, RN-44)** |
| POST | `/api/chamados/{id}/visitas/{v}/finalizar-dados` | técnico | — | **410 Gone** | **Descontinuado (implementado).** Nome, CPF e assinatura vão somente em `finalizar-atendimento` |
| GET | `/api/chamados/{id}/visitas/{v}/assinatura` | admin ou técnico atribuído | — | Imagem (`image/png` ou `image/jpeg`), `Cache-Control: private, no-store`, `nosniff` | **Implementado (v0.6, teste SQLite).** Decifra a assinatura em memória. Mesma autorização por OS de `carregar_chamado` (técnico de outra OS → 403; sem token → 401). Sem assinatura/arquivo → 404. `.enc` adulterado → 500 "Assinatura ilegível" (e log de erro). Assinaturas antigas em claro ainda são lidas até a conversão (`cifrar_dados_existentes.py`) |
| GET | `/api/chamados/{id}/verificar-integridade` | admin | — | `{id_os, estado, visitas:[{id_visita, estado, motivos[]}]}` | **Implementado (v0.6, teste SQLite).** `estado` por visita: `integro`, `adulterado`, `sem_selo` ou `nao_finalizada`; da OS: `adulterado` se qualquer visita estiver, senão `integro`, `sem_selo` ou `nao_finalizada`. Recalcula o selo (HMAC, `compare_digest`) **e** re-hasheia os arquivos em disco. `motivos`: `selo_divergente`, `versao_do_selo_desconhecida`, `arquivo_divergente:<campo>`, `arquivo_ausente:<campo>`, `arquivo_adulterado:<campo>`. Somente leitura (além da auditoria `INTEGRIDADE_VERIFICADA`) |

**6.6.1 `IniciarDeslocamento` (exemplo)**

```json
{ "tipo": "ida", "km_inicio": 124562 }
```

**6.6.2 `Pausar` (exemplo)**

```json
{ "motivo": "Peça pendente", "descricao": "Aguardando compressor de reposição" }
```

**6.6.3 `EstadoVisita`**

```json
{
  "pode_iniciar_deslocamento_ida": false,
  "pode_finalizar_deslocamento_ida": false,
  "pode_iniciar_atendimento": true,
  "pode_finalizar_atendimento": false,
  "pode_iniciar_deslocamento_volta": false,
  "pode_finalizar_deslocamento_volta": false,
  "pode_concluir_chamado": false,
  "pode_pausar_os": false,
  "is_os_pausada": false,
  "motivo_pausa": null
}
```

**v0.5 — campos novos do `EstadoVisita` (implementado no backend, testes em SQLite)**

```json
{
  "pode_registrar_foto_defeito": true,
  "atendimento_em_andamento": false,
  "bloqueio_iniciar_atendimento": "Falta a foto do defeito de: Freezer vertical modelo X (série FZ-88422)",
  "bloqueio_finalizar_atendimento": null,
  "equipamentos": [
    { "id_os_equipamento": 12, "id_servico": 301, "modelo": "Freezer vertical modelo X",
      "numero_serie": "FZ-88421", "foto_defeito": true, "conserto_salvo": false, "foto_conserto": false },
    { "id_os_equipamento": 13, "id_servico": 302, "modelo": "Freezer vertical modelo X",
      "numero_serie": "FZ-88422", "foto_defeito": false, "conserto_salvo": false, "foto_conserto": false }
  ]
}
```

- `pode_iniciar_atendimento` passa a exigir ida finalizada **e** todos os equipamentos com `foto_defeito = true` **e** OS com equipamento. `pode_finalizar_atendimento` passa a exigir, além das condições atuais, todos com `conserto_salvo` e `foto_conserto`.
- `atendimento_em_andamento` é verdadeiro com o atendimento iniciado, não finalizado e visita vigente (inclusive pausada); o app o usa para liberar "Salvar conserto" e a foto de conserto sem depender de heurísticas.
- `pode_registrar_foto_defeito` é verdadeiro com a visita vigente aberta, atendimento não finalizado e OS `Agendado` ou `Em Atendimento`, para a tela exibir o botão de foto **antes** de iniciar.
- `bloqueio_*` trazem o texto a exibir (o mesmo `detail` que o servidor devolveria com 409); `null` quando não há bloqueio. O app mostra os botões desabilitados com a pendência, nunca os esconde.
- Visita não vigente: `equipamentos = []`, `bloqueio_* = null` e os booleanos continuam `false`.

**6.6.4 `ocorrido_em` (implementado)**

- Campo **opcional** `ocorrido_em` nos corpos de `iniciar-deslocamento`, `finalizar-deslocamento`, `iniciar-atendimento`, `pausar` e `finalizar-atendimento`: ISO-8601 **com fuso** (ex.: `2026-11-07T14:02:11-03:00`), vindo do aparelho (AR-05, RN-24).
- Se informado sem fuso → 422. Se estiver mais de **5 minutos no futuro** → 422 com mensagem que pede conferir o relógio do aparelho. Se omitido, o servidor usa o instante atual (UTC).
- O instante é gravado em `ida_inicio_em`, `ida_fim_em`, `atendimento_inicio_em`, `atendimento_fim_em`, `volta_inicio_em` e `volta_fim_em` (UTC) e usado para derivar as colunas legadas `hora_*` em `HH:mm` no fuso `America/Sao_Paulo`. A correção de desvio de relógio (SY-04) faz parte da sincronização offline, ainda pendente.

**6.6.5 `Visita` (resposta, implementado)**

Além dos campos de 4.4, a resposta de visita inclui `assinatura_url`, `nome_cliente_assinatura`, `documento_cliente` (CPF do cliente, 11 dígitos), os seis instantes `*_em` (UTC) e `pausas[]`:

```json
{
  "id_visita": 77,
  "id_os": 41,
  "assinatura_url": "chamados/41/visitas/77/assinatura/ab12cd34.png",
  "nome_cliente_assinatura": "Maria Souza",
  "documento_cliente": "52998224725",
  "ida_inicio_em": "2026-11-09T17:02:11Z",
  "ida_fim_em": "2026-11-09T17:40:02Z",
  "atendimento_inicio_em": "2026-11-09T17:45:00Z",
  "atendimento_fim_em": null,
  "volta_inicio_em": null,
  "volta_fim_em": null,
  "pausas": [
    {
      "id_pausa": 9, "visita_id": 77, "motivo": "Peça pendente", "descricao": null,
      "criado_em": "2026-11-09T19:10:00Z", "encerrada_em": null, "is_ativa": true,
      "por_usuario_id": 3, "por_papel": "tecnico"
    }
  ]
}
```

Os campos de instante não preenchidos vêm `null`. O exemplo é ilustrativo; `assinatura_url` continua sendo referência ao arquivo até a migração para o Storage privado (seção 9).

### 6.7 Serviços por equipamento

> **v0.5 (implementado no backend; testes em SQLite).** O equipamento vem da OS. O registro de serviço de cada equipamento é criado **pelo servidor** (6.5.3); o técnico só o preenche. A tabela abaixo já reflete o contrato v0.5; as linhas alteradas estão marcadas.

| Método | Rota | Papel | Entrada | Saída |
|---|---|---|---|---|
| GET | `/api/chamados/{id}/visitas/{v}/servicos` | autenticado | — | `ServicoEquipamento[]` (um por equipamento da OS na visita, com `modelo` e `numero_serie` somente leitura) |
| POST | `/api/chamados/{id}/visitas/{v}/servicos` | — | — | **410 Gone (v0.5).** O técnico não cria serviço nem equipamento (RN-42); o servidor cria o registro de cada `os_equipamento` junto com a visita |
| PATCH | `/api/chamados/{id}/visitas/{v}/servicos/{s}` | técnico atribuído | Parcial: defeitos, sub-defeitos, descrições e `materiais_utilizados` (6.7.1). **v0.5:** `numero_serie_atendido`, `nome_equipamento`, `id_os_equipamento` e qualquer campo de equipamento/modelo/série → **422** (schema com `extra = "forbid"`) | Serviço atualizado. Aceito com a visita vigente aberta e o atendimento não finalizado; 409 caso contrário. Deixar `defeitos_principais` vazio com `conserto_salvo_em` preenchido → 422 |
| POST | `/api/chamados/{id}/visitas/{v}/servicos/{s}/salvar-conserto` *(v0.5)* | técnico atribuído | `{ocorrido_em?}` | `ServicoEquipamento` com `conserto_salvo_em`. Exige atendimento **iniciado**, não finalizado (400) e **sem pausa ativa** (400), e **ao menos um defeito principal** (422). Idempotente: repetir mantém a primeira marca. Audita `CONSERTO_SALVO` (RN-47) |
| POST | `/api/chamados/{id}/visitas/{v}/servicos/{s}/upload-foto` | técnico | multipart: `file`, `tipo` (defeito/conserto) | `{status, url, tipo, id_foto}`. RN-21: resolução mínima equivalente a 960 × 1280 em qualquer orientação (menor lado ≥ 960 e maior lado ≥ 1280) **só para `conserto`** (PR-29). **v0.5 — regras de fase (PR-42):** `defeito` é aceito com a visita vigente aberta e a OS `Agendado` (antes de iniciar, RN-43) ou `Em Atendimento`; `conserto` só com a OS `Em Atendimento` (atendimento iniciado, não finalizado e sem pausa) — antes disso 409; qualquer foto de serviço enviada pelo **técnico** após o atendimento finalizado → 409 (a correção por **administrador** em OS `Finalizado` segue 6.13, RN-49). O `{s}` deve pertencer à visita `{v}` da OS `{id}` (senão 404) |
| GET | `/api/chamados/{id}/visitas/{v}/servicos/{s}/fotos` | autenticado | — | `{fotos_defeito: ServicoFotoResponse[], fotos_conserto: ServicoFotoResponse[]}`, onde cada item tem `id_foto`, `id_servico`, `tipo`, `url` |

**6.7.1 `ServicoEquipamento`**

*(v0.5)* **Entrada do técnico** (`PATCH`): apenas defeitos, descrições e materiais, como no exemplo. **Resposta**: além desses campos, traz `id_servico`, `id_os_equipamento`, `modelo`, `numero_serie` (somente leitura, vindos do vínculo), `conserto_salvo_em` (ou `null`), `is_legado` e as fotos por tipo. `numero_serie_atendido` e `nome_equipamento` **não existem mais na entrada**; só aparecem na resposta de serviços legados (`is_legado = true`).

Exemplo de **entrada** v0.5 (o exemplo anterior, com `numero_serie_atendido` e `nome_equipamento`, deixa de ser válido):

```json
{
  "defeitos_principais": ["Refrigeração"],
  "sub_defeitos_refrigeracao": ["Compressor"],
  "sub_defeitos_compressor": ["Queimado"],
  "sub_defeitos_vazamento": [],
  "vazamento_ponto_descricao": null,
  "sub_defeitos_outros": [],
  "sub_defeitos_iluminacao": [],
  "sub_defeitos_estrutura": [],
  "defeito_outros_descricao": null,
  "materiais_utilizados": [
    { "nome": "Compressor 1/4 HP", "quantidade": 1, "valor": 850.00 }
  ]
}
```

### 6.8 Padrão de payload de upload

- Imagens: JPEG ou PNG. O **formato real** é verificado no servidor (decodificação com Pillow), não pelo `Content-Type` nem pela extensão; arquivo vazio ou que não é JPEG/PNG → **422**. Implementado.
- Tamanho máximo **15 MB por arquivo de imagem**: a API lê em blocos e aborta com **413** ao passar do limite, sem persistir arquivo parcial (também vale para a assinatura em base64). Implementado na API; no app e na configuração do bucket permanece pendente.
- Resolução mínima **apenas para fotos de conserto**: equivalente a **960 × 1280 em qualquer orientação** (RN-21): **menor lado ≥ 960 e maior lado ≥ 1280** (aceitam-se 960 × 1280 e 1280 × 960; recusam-se 1000 × 1200 e 900 × 1500). O app valida na captura e o servidor valida de novo ao receber (400, "Resolução insuficiente"). Fotos de defeito, odômetro e deslocamento não têm mínimo.
- **Upload em OS `Finalizado` → 409** (OS finalizada não aceita novos arquivos). *(v0.5, exceção única)* O **administrador** pode enviar/substituir foto comprobatória de serviço (defeito/conserto) em OS `Finalizado` não cancelada, pelas rotas e regras de 6.13 (RN-49); o técnico continua recebendo 409.
- `/static` passa a responder com `X-Content-Type-Options: nosniff`. É mitigação, não substitui o acesso autorizado do SEG-09 (seção 9). **v0.6:** somente `/static/uploads` é servido; `/static/assinaturas` **não existe** (404).
- **Integridade (v0.6, SEG-24).** Todo upload (`upload-deslocamento`, `upload_file`, `servicos/{s}/upload-foto`, `/api/sync/arquivos`) aceita o campo multipart **`sha256`** (64 hex): o SHA-256 dos bytes **calculado no aparelho/navegador**. O servidor lê o corpo, recalcula e compara em tempo constante **antes** de qualquer outra análise: divergência → **422** `{detail, codigo:"HASH_DIVERGENTE"}` e **nada é gravado**; formato inválido → 422 `HASH_INVALIDO`; ausente com `SHA256_ORIGEM_OBRIGATORIO=true` → 422 `HASH_AUSENTE`. O servidor grava **sempre** o hash que ele mesmo calculou (`servico_foto.sha256`, `comprovante.sha256`, `sync_arquivo.sha256`, `visita.arquivos_sha256`, `visita.assinatura_sha256`). Para a assinatura em base64 (`finalizar-atendimento`) o campo é `assinatura_sha256`, conferido contra os bytes decodificados.
- O corpo de erro de regra (`ErroRegra`) passa a incluir **`codigo`** estável além de `detail`, para o cliente decidir se repete (ex.: `HASH_DIVERGENTE`).
- **Assinatura (v0.6, SEG-26).** Gravada **cifrada** (AES-256-GCM, AAD `fast-ariam-v1|arquivo.assinatura`) em `static/assinaturas/<uuid>.enc`. O hash é dos bytes originais (antes de cifrar). Leitura apenas por `GET .../assinatura` (6.6).
- Nome do arquivo gerado no servidor: `{prefixo}_{uuid8}{ext}`. Prefixo inclui `chamado_{id}_visita_{id}_{campo}`.

### 6.9 Cancelamento de OS

`POST /api/chamados/{id}/cancelar` · papel `admin` · corpo `{ "motivo": "texto" }`.

- **Entrada:** `motivo` obrigatório, não vazio, até 500 caracteres. Sem motivo: 422.
- **Permitido** em qualquer status, inclusive Pendente, Em Atendimento, Pausado e Aguardando Reagendamento. **Finalizado** e OS já cancelada retornam 409 (decisão confirmada).
- **Efeitos:** `is_cancelled = true`, `motivo_cancelamento`, `cancelado_em`, `cancelado_por`. As pausas ativas são encerradas. Visitas, fotos e serviços já registrados são mantidos.
- **Saída:** `Chamado` atualizado. O `DELETE /api/chamados/{id}` é removido (PR-28).
- **Painel:** deixa de concatenar o motivo na `descricao_cliente` e deixa de enviar o status `CANCELADO`.
- **App:** uma OS cancelada some da lista após a sincronização. Ações offline pendentes dessa OS são rejeitadas com o código `OS_CANCELADA`, e o técnico vê o motivo (6.12).

### 6.10 Reagendamento e pausa pelo administrador

`POST /api/chamados/{id}/reagendar` · papel `admin` · corpo `{ "data_visita": "2026-11-05" }`.

| Status da OS | Permitido | Efeito |
|---|:---:|---|
| Pendente | ❌ 409 | Atribuir técnico primeiro |
| Agendado, ida não iniciada | ✅ | Altera `data_visita` da visita existente e `data_agendamento` da OS; não cria visita vazia |
| Agendado, ida iniciada | ❌ 409 | Técnico já iniciou o deslocamento; não reagendar |
| Em Atendimento | ❌ 409 | Deve pausar e finalizar a volta |
| Pausado | ❌ 409 | O técnico deve finalizar o deslocamento de volta primeiro |
| Aguardando Reagendamento | ✅ | Cria nova visita, encerra a pausa e leva OS para Agendado |
| Finalizado ou cancelada | ❌ 409 | Estado terminal |

*(v0.5)* Reagendar OS legada sem equipamento retorna 409 (TR-15).

Regras adicionais do reagendamento (implementadas): `data_visita` no passado (comparada ao dia atual em `America/Sao_Paulo`) → **422**; a OS precisa ter **técnico ativo** atribuído, caso contrário **409** (por exemplo, técnico desativado). Reagendar `Agendado` com ida não iniciada devolve 200 (data alterada); reagendar `Aguardando Reagendamento` devolve 201 (nova visita).

`POST /api/chamados/{id}/visitas/{v}/pausar` aceita papel `admin` ou `tecnico` atribuído:

- Mesma regra de estado para ambos: somente com a visita em atendimento e não finalizada.
- `por_usuario_id` e `por_papel` recebem o id e o papel de quem pausou.
- Pausada, a visita não pode finalizar atendimento; o deslocamento de volta continua permitido.
- O reagendamento não pode ocorrer até que o deslocamento de volta seja concluído e a OS passe para `Aguardando Reagendamento`.

### 6.11 Valores globais de referência de custo

Os valores de primeira hora, hora adicional, tempo de deslocamento e quilometragem são globais, definidos na configuração central do sistema. Não são individualizados por técnico e não podem ser alterados pelo app do técnico.

| Configuração | Origem | Regra |
|---|---|---|
| `primeira_hora_tecnico` | Configuração global do backend/registro central | Valor aplicado à primeira hora de serviço |
| `hora_tecnico` | Configuração global do backend/registro central | Valor horário adicional, aplicado proporcionalmente |
| `tempo_deslocamento_tecnico` | Configuração global do backend/registro central | Valor de referência do deslocamento, conforme fórmula de custo aprovada |
| `quilometragem` | Configuração global do backend/registro central | Valor por quilômetro |

Não implementar `GET/PUT /api/tecnicos/me/configuracao-custo` nem `GET /api/tecnicos/{id}/configuracao-custo`. Não criar tela de configuração para técnico. A alteração dos valores é uma operação central de configuração do sistema; não há requisito nesta versão para UI administrativa de edição.

- Valores devem ser números ≥ 0 com 2 casas decimais.
- O cálculo considera materiais, quilometragem, pedágio, frete, tempo de deslocamento e tempo de serviço. Ajudantes estão fora do escopo v0.3 e não entram em campos novos nem no cálculo.
- **Congelamento obrigatório:** ao finalizar a OS, gravar em `custo_os` o total, detalhes e cópia dos valores globais utilizados. `GET .../custos` devolve o snapshot para OS finalizada e o cálculo atual para as demais.
- **Tempo de serviço de visita pausada (decisão do PO, 07/11/2026):** conta **ZERO** no custo, porque o atendimento não foi finalizado. Deslocamento, quilometragem, pedágio, frete e materiais continuam entrando. Vale para o cálculo e para o snapshot.
- **Resposta de `GET /api/chamados/{id}/custos` (implementado):** além do total e dos detalhes, devolve `congelado` (true quando vem do snapshot de OS finalizada), `calculado_em` e `valores_utilizados` (cópia dos valores globais usados no cálculo).
- O custo é só registro interno. Não existe fluxo de cobrança do cliente.

### 6.12 Sincronização offline

> **Status (08/11/2026):** contrato fechado nesta seção. **Backend implementado** (`/api/sync/arquivos`, `/eventos`, `/minhas-os`; serviço `sync_service`) e coberto por `backend/tests/chamados/test_sync.py` em SQLite. A tabela `sync_evento` já existia; a v0.5 acrescenta `sync_arquivo` (migração `0009_sync_arquivo.sql`, **aplicada no Supabase real em 08/11/2026**). A situação do app está descrita no fim da seção.

**Objetivo:** o app grava as ações no aparelho e as envia quando há conexão, sem perder, duplicar nem reordenar.

**Endpoints** (papel `tecnico`; técnico inativo ou token expirado → 401 para o lote inteiro)

| Método | Rota | Entrada | Saída |
|---|---|---|---|
| POST | `/api/sync/arquivos` | multipart: `client_file_id` (UUID), `file`, `tipo_arquivo`, `id_os`, `id_visita`, **`sha256`** *(v0.6; obrigatório com `SHA256_ORIGEM_OBRIGATORIO=true`)* | `{client_file_id, url, resultado, sha256}` (`aplicado` ou `duplicado`; `sha256` = hash que o servidor gravou) |
| POST | `/api/sync/eventos` | lote de eventos (abaixo) | `{"resultados": [ {client_event_id, resultado, codigo, detalhe} ]}`, na ordem recebida |
| GET | `/api/sync/minhas-os?desde=<iso>` | — | `{sincronizado_em, os: [...]}` para o cache local |

**Arquivos** (`POST /api/sync/arquivos`)

- `tipo_arquivo` ∈ `foto_defeito`, `foto_conserto`, `foto_deslocamento`, `comprovante_pedagio`, `comprovante_frete`, `assinatura`.
- Mesmas validações do upload online (6.8): JPEG/PNG real (422), 15 MB (413), e para `foto_conserto` resolução 960 × 1280 em qualquer orientação (400). `assinatura` é um PNG/JPEG da assinatura manuscrita (não base64).
- A OS/visita informadas devem ser do técnico (OS de outro técnico → 403; inexistente → 404). OS cancelada: o arquivo é aceito e guardado, e o evento que o referencia é rejeitado com `OS_CANCELADA`; OS Finalizada → 409.
- O servidor **guarda o arquivo e o associa ao `client_file_id`** (tabela `sync_arquivo`); a ligação ao registro final (foto do serviço, odômetro, comprovante, assinatura) só ocorre quando o evento que o referencia (`foto_ref` / `assinatura_ref`) é aplicado. Reenviar o mesmo `client_file_id` devolve a `url` já gravada com `resultado = "duplicado"`, sem novo arquivo.
- **O app envia os arquivos ANTES dos eventos que os referenciam** (SY-08).
- **Integridade (v0.6).** O app calcula o SHA-256 **na captura** (quando o arquivo entra na fila, não no envio) e o guarda no SQLite (`outbox_arquivos.sha256`, schema v2); assim a verificação cobre também as horas offline. Arquivos já enfileirados por versão antiga do app (sem hash) têm o hash calculado no envio. O servidor recalcula; divergência → 422 `HASH_DIVERGENTE`, e o app **repete o envio** (até 5 tentativas; o arquivo nunca é apagado) antes de marcá-lo como `rejeitado` com o motivo. Reenvio do **mesmo `client_file_id` com hash diferente** → **409 `ARQUIVO_DIVERGENTE`** (nunca tratado como `duplicado`). `visita.assinatura_sha256` e os demais hashes são copiados do `sync_arquivo` quando o evento que o referencia é aplicado.

**Lote de eventos**

```json
{
  "dispositivo_id": "uuid-do-aparelho",
  "enviado_em": "2026-11-09T21:15:04-03:00",
  "eventos": [
    {
      "client_event_id": "6f1c0a52-3b7e-4d0e-9a41-2c8f6b1d7e90",
      "tipo": "deslocamento_ida_iniciado",
      "id_os": 41,
      "id_visita": 77,
      "ocorrido_em": "2026-11-09T14:02:11-03:00",
      "payload": { "km_inicio": 124562, "foto_ref": "b2a1c9e4-0a3f-4b61-8d52-7e9c4f1a6b33" }
    }
  ]
}
```

`ocorrido_em` é ISO-8601 **com fuso**. Máximo de 200 eventos por lote.

**Tipos de evento e `payload`** (todos usam os MESMOS serviços do fluxo online, com `ocorrido_em` no lugar de "agora")

| `tipo` | `payload` | Equivale ao endpoint online |
|---|---|---|
| deslocamento_ida_iniciado | `km_inicio`, `foto_ref?` (`foto_deslocamento`) | `iniciar-deslocamento` (ida) + foto de início |
| deslocamento_ida_finalizado | `km_fim`, `foto_ref?` | `finalizar-deslocamento` (ida) + foto de fim |
| atendimento_iniciado | — | `iniciar-atendimento` (TR-12: foto de defeito de cada equipamento) |
| servico_salvo | `id_servico` **ou** `id_os_equipamento` + campos de `ServicoEquipamentoUpdate` (6.7.1; sem série nem nome) | `PATCH .../servicos/{s}` |
| conserto_salvo | `id_servico` **ou** `id_os_equipamento` | `salvar-conserto` |
| foto_servico | `id_servico` **ou** `id_os_equipamento`, `tipo` (`defeito`/`conserto`), `foto_ref` (`foto_defeito`/`foto_conserto`) | `upload-foto` |
| comprovante_registrado | `tipo` (`pedagio`/`frete`), `valor?` (≥ 0), `foto_ref` (`comprovante_*`) | `upload_file` + valor da visita |
| pausa_registrada | `motivo`, `descricao?` | `pausar` |
| atendimento_finalizado | `nome_cliente`, `documento_cliente` (CPF), `assinatura_ref` (`assinatura`) | `finalizar-atendimento` (TR-13) |
| deslocamento_volta_iniciado | `km_inicio`, `foto_ref?` | `iniciar-deslocamento` (volta) + foto |
| deslocamento_volta_finalizado | `km_fim`, `foto_ref?` | `finalizar-deslocamento` (volta) + foto de fim (RN-19) |

`id_servico` e `id_os_equipamento` vêm do cache de `minhas-os`; o técnico nunca cria equipamento nem serviço (RN-42).

**Resposta, por evento**

```json
{ "client_event_id": "6f1c...", "resultado": "aplicado", "codigo": null, "detalhe": null }
```

`resultado`: `aplicado`, `duplicado` (já processado: devolve `codigo`/`detalhe` do resultado anterior) ou `rejeitado`.

**Códigos de rejeição**

| `codigo` | Quando |
|---|---|
| OS_CANCELADA | A OS foi cancelada |
| OS_PAUSADA | Há pausa ativa feita pelo técnico que impede o evento (ex.: finalizar atendimento) |
| OS_REATRIBUIDA | A OS não é mais do técnico, ou a visita não é mais a executável |
| CONFLITO_ADMINISTRATIVO | Ação incompatível com alteração do administrador (SY-05, SY-09): OS movida para Pendente |
| TRANSICAO_INVALIDA | O evento não é válido no estado atual (TR-01), inclusive OS já Finalizada |
| DEPENDENCIA_REJEITADA | Um evento anterior da mesma visita, no mesmo lote, foi rejeitado |
| FOTO_DEFEITO_AUSENTE | `atendimento_iniciado` sem foto de defeito de algum equipamento (TR-12) |
| CONSERTO_INCOMPLETO | `atendimento_finalizado` sem conserto salvo ou sem foto de conserto de algum equipamento (TR-13) |
| ARQUIVO_AUSENTE | O `foto_ref`/`assinatura_ref` ainda não foi enviado. **Transitório: não é gravado**; reenviar o MESMO `client_event_id` depois do arquivo |
| VALIDACAO | CPF inválido, tipo de evento desconhecido, campos obrigatórios ausentes, série/modelo no payload de serviço, equipamento fora da OS, comprovante ausente etc. |

**Regras de processamento**

- **SY-01** Dentro do lote, os eventos são processados por `ocorrido_em` (empate: ordem recebida). Se um evento de uma visita é rejeitado, os seguintes **da mesma visita no mesmo lote** recebem `DEPENDENCIA_REJEITADA` (gravados). Entre lotes não há dependência: cada evento é avaliado pelo estado real da OS.
- **SY-02** Cada evento passa pelas mesmas regras e serviços do endpoint online.
- **SY-03** `client_event_id` é chave primária em `sync_evento`. Reenviar é seguro (`duplicado`).
- **SY-04** Relógio do aparelho: `desvio = recebido_em − enviado_em`; se `|desvio| > 2 min`, `ocorrido_em` é corrigido somando o desvio (limitado a `recebido_em`). O valor original fica em `payload.ocorrido_em_original`.
- **SY-05** Conflito administrativo: um evento é `CONFLITO_ADMINISTRATIVO` quando (a) referencia equipamento/serviço removido ou alterado pelo administrador (SY-09), ou (b) esbarra em **pausa feita pelo administrador** (`pausa.por_papel = 'admin'`) que impede o evento. Efeitos, numa transação: o evento é rejeitado e gravado; se a OS **não** está Finalizada nem cancelada, ela passa a `Pendente`, sem técnico, as pausas ativas são encerradas, e a ação `CONFLITO_ADMINISTRATIVO` é auditada em `log_acao`. Eventos anteriores e compatíveis (já aplicados) permanecem. Cancelamento e finalização já efetivados não são revertidos.
- **SY-06** A transação é por **evento**: o registro em `sync_evento` e o efeito do evento são confirmados juntos. Um evento rejeitado não desfaz os outros; eventos e arquivos rejeitados permanecem rastreáveis, nunca apagados silenciosamente.
- **SY-07** Toda OS em `Pendente` fica sem técnico. A sincronização não reatribui automaticamente.
- **SY-08** O app envia os arquivos antes dos eventos que os referenciam; evento com arquivo ainda não recebido é `ARQUIVO_AUSENTE` (transitório). Rejeições por pré-condição (`FOTO_DEFEITO_AUSENTE`, `CONSERTO_INCOMPLETO`) são gravadas: o app corrige (ex.: envia a foto) e reenvia a ação com **novo** `client_event_id`.
- **SY-09** Evento que referencia equipamento removido ou alterado pelo administrador durante o período offline → `CONFLITO_ADMINISTRATIVO` (SY-05); fotos e eventos locais são preservados e o motivo é mostrado ao técnico.

**`GET /api/sync/minhas-os`**

Devolve **todas** as OS atribuídas ao técnico e não canceladas, para substituir o cache local (o app remove do cache o que não vier). Cada item: `chamado` (o mesmo `Chamado` de 6.5, com `equipamentos[]`, visitas e serviços com `id_servico`) e `estado_visita_vigente` (o `EstadoVisita` de 6.6.3 da visita executável, ou `null`). O parâmetro `desde` é aceito mas **ainda não filtra** (não há coluna de atualização na OS); o servidor devolve sempre o conjunto completo e informa `sincronizado_em`.

**Aplicativo (Android)**

- **Armazenamento local:** banco SQLite (`expo-sqlite`) com `os_cache`, `outbox_eventos` e `outbox_arquivos`. Fotos e assinatura ficam no armazenamento do app até o envio confirmado.
- **Offline-first (AR-04):** toda ação grava primeiro no aparelho (evento na outbox, com `client_event_id` e `ocorrido_em` do relógio local) e é enviada em seguida, se houver conexão. A tela lê o estado local.
- **Estado da visita offline:** o app calcula localmente os mesmos campos de `GET .../estado` (6.6.3) a partir dos eventos locais e do último estado do servidor. As regras de derivação ficam num único módulo, espelhando `calcular_estado` do backend. O servidor continua sendo a autoridade (409/rejeição).
- **Fila:** envio ao abrir o app, ao voltar a conexão e a cada intervalo, com espera crescente após falha. **Arquivos saem antes dos eventos** e os eventos saem em ordem de `ocorrido_em`. Reenvio idempotente.
- **Foto de conserto:** validada no aparelho (960 × 1280, qualquer orientação) ao capturar; foto abaixo disso é recusada na hora. Não reduzir a resolução na compressão.
- **Foto de defeito antes de iniciar:** entra na outbox antes de `atendimento_iniciado`; o app só espelha localmente TR-12/TR-13 para habilitar botões.
- **Sessão:** login inicial exige internet. O app opera offline por até 24 horas desde a última autenticação online bem-sucedida. Não há refresh token. O JWT mantém a expiração configurada (30 minutos); se expirar, a fila local permanece íntegra e uma nova autenticação online é exigida antes de sincronizar. Após 24 horas offline, bloqueia novas operações autenticadas até reconexão e login; **nunca apaga a outbox**.
- **Cache de OS (v0.5):** `minhas-os` traz equipamentos e `servico_equipamento` com `id_servico`; sem esse cache a OS não abre offline e o app mostra erro claro. O catálogo de modelos **não** é baixado.
- **Estados por ação:** `pendente de envio`, `enviada` ou `rejeitada` (com o motivo). O técnico vê a lista de rejeitadas; a fila não trava por causa delas.
- **Token e dados locais:** em armazenamento seguro do Android (SEG-13).

**Situação do app (08/11/2026):** implementado em `frontend/src/offline/` (SQLite `os_cache`/`outbox_eventos`/`outbox_arquivos`, motor de sincronização arquivos → eventos → `minhas-os`, estado local espelhando `calcular_estado`, sessão offline de 24 h sem refresh token, tela de pendências/rejeitadas). `tsc` e `lint` sem erros; **não executado em aparelho nem contra o backend**. Requer **novo build nativo** (módulos `expo-sqlite`, `expo-file-system`, `expo-crypto`, `@react-native-community/netinfo`). Limitações conhecidas: SQLite e fotos do app ficam no sandbox **sem criptografia** (só token e sessão em SecureStore); o limite de 24 h depende do relógio do aparelho; reenvio de ação rejeitada usa o horário de agora; pedágio/frete exigem foto a cada valor; as pendências ficam separadas por técnico no aparelho; não há limite de tentativas para `ARQUIVO_AUSENTE`.

### 6.13 Catálogo de equipamentos e equipamentos da OS (v0.5)

> **Implementado no backend (testes em SQLite).** Referências: PRD 6.10 (RF-23 a RF-25, RN-40 a RN-49).

**Catálogo `/api/equipamentos`** (papel `admin`; técnico não acessa — recebe os equipamentos embutidos na OS)

| Método | Rota | Entrada | Saída e erros |
|---|---|---|---|
| POST | `/api/equipamentos/` | `{modelo}` (1 a 100 caracteres, trim) | 201 `EquipamentoModelo{id_equipamento_modelo, modelo, is_active}`. 409 se o modelo já existe (sem diferenciar maiúsculas); 422 se inválido |
| GET | `/api/equipamentos/?is_active=` | — | `EquipamentoModelo[]` |
| GET | `/api/equipamentos/{id}` | — | `EquipamentoModelo` ou 404 |
| PATCH | `/api/equipamentos/{id}` | `{modelo?, is_active?}` | 200. 409 se o nome duplicar. Renomear é auditado e afeta a exibição do histórico (PR-45). Reativar é permitido |
| DELETE | `/api/equipamentos/{id}` | — | 204 = **desativação lógica** (`is_active = false`). Nunca apaga; modelo em uso permanece nas OS existentes. Modelo inativo não pode ser vinculado a OS nova (422) |

**Equipamentos da OS `/api/chamados/{id}/equipamentos`**

| Método | Rota | Papel | Entrada | Saída e erros |
|---|---|---|---|---|
| GET | `/api/chamados/{id}/equipamentos` | admin; técnico atribuído | — | `OsEquipamento[]` = `{id_os_equipamento, id_equipamento_modelo, modelo, numero_serie}`. 403 se OS de outro técnico; 404 se cancelada |
| POST | idem | admin | `{id_equipamento_modelo, numero_serie}` | 201. 404 modelo inexistente; 422 modelo inativo ou série vazia; 409 se OS Finalizada/cancelada, se a visita vigente já iniciou o atendimento (RN-45) ou se `(id_os, série)` já existe. Cria o registro de serviço da visita aberta, se houver. Técnico → 403 |
| PATCH | `/{id_os_equipamento}` | admin | `{id_equipamento_modelo?, numero_serie?}` | 200. Mesmos erros do POST; 409 também após o início do atendimento da visita vigente. Auditado |
| DELETE | `/{id_os_equipamento}` | admin | — | 204. 409 se for o **último** equipamento da OS, se houver conteúdo registrado (foto, defeito, material ou conserto salvo) em qualquer visita ou após o início do atendimento. Remove os registros de serviço vazios na mesma transação. Auditado |

- O `Chamado` (resposta de `POST/GET /api/chamados`) devolve `equipamentos[]` como acima.
- Número de série: normalizado com trim; unicidade por OS sem diferenciar maiúsculas; máximo 100 caracteres.
- **IDOR:** todo `id_os_equipamento`/`id_servico` recebido é validado contra a OS e a visita da URL (404 quando não pertence).
- **Auditoria em `log_acao`** (sem PII; payload só com ids e a série): `EQUIPAMENTO_MODELO_CRIADO`, `EQUIPAMENTO_MODELO_ATUALIZADO`, `EQUIPAMENTO_MODELO_DESATIVADO`, `OS_EQUIPAMENTO_VINCULADO`, `OS_EQUIPAMENTO_ALTERADO`, `OS_EQUIPAMENTO_REMOVIDO`, `SERVICO_ATUALIZADO`, `CONSERTO_SALVO`; `ATENDIMENTO_INICIADO` e `ATENDIMENTO_FINALIZADO` passam a registrar `equipamentos_conferidos`.
- **Concorrência:** as travas TR-12/TR-13 leem a visita com `SELECT ... FOR UPDATE`; alterações de equipamento pelo admin usam a mesma trava, para que vincular/remover equipamento e iniciar/finalizar o atendimento não deixem estado inconsistente.

**Correção administrativa de OS Finalizada (RN-49; confirmada em 08/11/2026)**

A edição do admin volta a ser possível **somente com a OS `Finalizado` e não cancelada**, e **só** para fotos comprobatórias e materiais. Do início do atendimento até a finalização, o equipamento fica travado (RN-45). Modelo e número de série permanecem travados também em OS Finalizada (decisão do responsável: só fotos e materiais são editáveis após a finalização).

| Método | Rota | Papel | Entrada | Saída e erros |
|---|---|---|---|---|
| POST | `/api/chamados/{id}/visitas/{v}/servicos/{s}/upload-foto` | admin (em OS Finalizada) | multipart: `file`, `tipo` (`defeito`/`conserto`) | Mesmas validações de 6.8 (JPEG/PNG real, 15 MB, conserto 960 × 1280). Técnico → 409 em OS Finalizada. OS não Finalizada, ou cancelada → 409 para o admin (fora da janela de correção) |
| DELETE | `/api/chamados/{id}/visitas/{v}/servicos/{s}/fotos/{id_foto}` *(novo)* | admin (em OS Finalizada) | — | 204. **409 se for a última foto do tipo** (`defeito` ou `conserto`) daquele equipamento: para trocar, envie a nova antes e depois remova a antiga. Técnico → 403 |
| PATCH | `/api/chamados/{id}/visitas/{v}/servicos/{s}` | admin (em OS Finalizada) | **somente** `materiais_utilizados`; qualquer outro campo → 422 | `ServicoEquipamento` atualizado. Técnico → 409/403. Defeitos, descrições, conserto salvo, assinatura, km e horários não mudam |

- Vale para qualquer visita da OS (cada foto/serviço pertence a uma visita), com `{s}` validado contra a visita e a OS da URL (SEG-21).
- **Auditoria obrigatória** em `log_acao` (quem, quando, `id_os`, `id_visita`, `id_servico`): `FOTO_CORRIGIDA_ADMIN` (enviada/removida, `id_foto`, `tipo`) e `MATERIAIS_CORRIGIDOS_ADMIN` (lista antes/depois). A referência à imagem removida é preservada no log; o arquivo removido não é apagado do armazenamento nesta versão (sem rotina de purga, RNF-02).
- **Custo recalculado (decisão do responsável, 08/11/2026):** a correção de **materiais** recalcula o custo da OS. O recálculo usa os materiais corrigidos e os **`valores_utilizados` já gravados no snapshot da finalização** (não a configuração global atual), preservando RN-33; o snapshot de `custo_os` é **substituído** (`total`, `detalhes`, `calculado_em`; `valores_utilizados` inalterado) na mesma transação da correção, e o `log_acao` `MATERIAIS_CORRIGIDOS_ADMIN` guarda `custo_total_anterior` e `custo_total_novo`. `GET .../custos` continua devolvendo `congelado = true` com o novo total. Correção apenas de fotos não recalcula nada.
- A OS permanece `Finalizado`; a correção não reabre atendimento, não altera status nem dispara transição (5.1).
- O painel exibe as ações de correção apenas em OS Finalizada; nos demais estados mostra o equipamento e as evidências somente para leitura.

## 7. Regras de validação consolidadas

| Entidade | Campo | Regra | Implementação |
|---|---|---|---|
| Visita | `km_total` | > 0 no schema de criação; ≥ 0 no de atualização | `VisitaBase` vs `VisitaCreate`. **Conflito, unificar** |
| Visita | Horários | `ocorrido_em` ISO-8601 com fuso, opcional; sem fuso ou > 5 min no futuro → 422 (6.6.4). Instantes `*_em` em `TIMESTAMPTZ` (UTC) | Implementado nos endpoints online (PR-30); offline pendente. `hora_*` `HH:mm` permanece como legado |
| Visita | Finalização | Se `km_total > 0`: odômetro início e fim | Em `update_visita_em_chamado` e `update_visita_e_chamado` |
| Visita | Finalização | Se `valor_pedagio > 0`: comprovante de pedágio | Idem |
| Visita | Finalização | Se `valor_frete_devolucao > 0`: comprovante de frete | Idem |
| Pausa | `motivo` | Um de: `Peça pendente`, `Cliente ausente`, `Condições inseguras`, `Aguardando aprovação`, `Outro` | Enum no backend. Painel e app usam a mesma lista (PR-15) |
| Pausa | `descricao` | Obrigatória (não vazia) quando `motivo = "Outro"` | Validador no schema |
| OS | `status` | `Pendente`, `Agendado`, `Em Atendimento`, `Pausado`, `Aguardando Reagendamento`, `Finalizado`; `Aberto` somente legado | Adicionar validador de transição e migrar valores legados |
| Técnico | `dados_bancarios` | banco, agência e conta obrigatórios | `DadosBancarios` |
| Técnico | `email` e `cnpj` | Únicos | Constraint do banco; CNPJ comparado na forma canônica |
| Técnico | `cpf` e `cnpj` | Armazenar com máscara canônica: CPF `000.000.000-00` (14 caracteres), CNPJ `00.000.000/0000-00` (18 caracteres) | Normalização no schema/serviço (6.3.1) |
| OS | `id_tecnico_atribuido` | Usuário ativo com papel `tecnico`; administrador não é atribuível | Serviço de OS (TR-11) |
| Cliente | `uf` | 2 letras maiúsculas | Adicionar validador |
| Cliente | `codigo` | Obrigatório, inteiro, único | Schema hoje opcional (PR-27) |
| Visita (assinatura) | `documento_cliente` | CPF **do cliente** válido: 11 dígitos, não repetidos, dígitos verificadores corretos. Guardar **só dígitos (11)** | Validador único (PR-34). Diferente do CPF do técnico, que usa máscara canônica |
| OS (cancelamento) | `motivo` | Obrigatório, não vazio, ≤ 500 caracteres | Schema de `cancelar` |
| Foto de serviço | resolução | Se `tipo = conserto`: menor lado ≥ 960 **e** maior lado ≥ 1280 (qualquer orientação). `defeito`: sem mínimo | `upload_foto_servico` (PR-29) e app |
| Imagem | tamanho e formato | ≤ 15 MB por arquivo (413); formato real JPEG/PNG (422); OS `Finalizado` não aceita arquivo (409) | API implementada; app e bucket privado pendentes |
| Configuração de custo | valores | Globais, números ≥ 0, 2 casas; sem configuração por técnico | Configuração central do backend |
| Custo | tempo de serviço | Visita pausada conta zero de tempo de serviço (6.11) | Serviço de custo |
| EquipamentoModelo *(v0.5)* | `modelo` | Obrigatório, trim, 1 a 100 caracteres, único sem diferenciar maiúsculas (409) | Índice único em `lower(modelo)` + serviço |
| OS *(v0.5)* | `equipamentos` | Mínimo 1 na criação (422); séries não repetidas na lista; modelo existente e ativo | Schema `ChamadoCreate` + serviço de OS |
| OsEquipamento *(v0.5)* | `numero_serie` | Obrigatório, trim, ≤ 100, único por OS sem diferenciar maiúsculas (409) | Índice único em `(id_os, upper(numero_serie))` + serviço |
| OsEquipamento *(v0.5)* | alteração/remoção | Só com OS não Finalizada/cancelada e atendimento da visita vigente não iniciado; remoção só sem conteúdo registrado e nunca do último (409) | Serviço (6.13) |
| Serviço *(v0.5)* | entrada do técnico | `numero_serie_atendido`, `nome_equipamento`, `id_os_equipamento` proibidos (422); `id_os_equipamento`/`id_servico` devem pertencer à OS/visita da URL (404) | Schema com `extra = "forbid"` |
| Início do atendimento *(v0.5)* | foto de defeito | ≥ 1 `servico_foto(tipo = 'defeito')` por equipamento da OS na visita; OS com ≥ 1 equipamento (409) | `visita_service.iniciar_atendimento` (TR-12) |
| Finalização do atendimento *(v0.5)* | conserto | Por equipamento da OS na visita: `conserto_salvo_em` preenchido e ≥ 1 `servico_foto(tipo = 'conserto')` (409) | `visita_service.finalizar_atendimento` (TR-13) |
| Conserto salvo *(v0.5)* | `salvar-conserto` | ≥ 1 defeito principal (422); atendimento iniciado, não finalizado, sem pausa (400) | Serviço (RN-47) |
| Foto de serviço *(v0.5)* | fase | Técnico: `defeito` com OS `Agendado`/`Em Atendimento`; `conserto` só `Em Atendimento`; nada após atendimento finalizado (409). Admin: somente correção em OS `Finalizado` não cancelada (RN-49) | `upload_foto_servico` (PR-42) |
| Correção pós-finalização *(v0.5)* | fotos e materiais | Só admin, só OS `Finalizado` não cancelada; não remover a última foto de `defeito`/`conserto` do equipamento (409); só `materiais_utilizados` no PATCH (422 para outros campos); auditoria obrigatória | Serviço (6.13) |

## 8. Segurança

**Legenda de status (v0.4).** *Implementado (teste SQLite)*: o código existe no backend e há teste automatizado rodando em SQLite temporário; **não** foi verificado em PostgreSQL/Supabase, em produção nem pelo QA/Security, portanto **não deve ser tratado como controle verificado**. *Parcial*: parte do controle existe. *Pendente*: não implementado. *A verificar*: sem evidência. Controle só passa a "verificado" com teste reproduzível em ambiente equivalente ao de produção e parecer do Security/QA.

| ID | Requisito | Situação (07/11/2026) |
|---|---|---|
| SEG-01 | Validar, a cada requisição, se o técnico ainda está ativo | **Implementado (teste SQLite).** `get_current_user` consulta o banco; inexistente, inativo ou e-mail divergente → 401 único; papel vem do banco |
| SEG-02 | Mensagem única para login inválido, inativo ou inexistente | **Implementado (teste SQLite).** 401 "Email ou senha incorretos" nos três casos, com bcrypt fictício para igualar o tempo. Resistência a enumeração por tempo não medida |
| SEG-03 | Origens permitidas por variável de ambiente (`CORS_ORIGINS`) | **Implementado (teste SQLite).** Obrigatória em produção, `*` recusado. Configuração real de produção não verificada |
| SEG-04 | Token em armazenamento do navegador sem exposição a XSS | **Pendente (PR-17).** Considerar cookie `HttpOnly` |
| SEG-05 | Guarda de ambiente em `resetar_banco.py` (recusar se `ENV=production`) | **Implementado (teste SQLite).** Recusa `ENV=production`, exige `DATABASE_URL`, recusa host remoto sem `--allow-remote`, pede confirmação; `AUTO_CREATE_TABLES` recusado em produção. **Ressalva de SEG:** com dev e produção no mesmo projeto Supabase (risco aceito pelo PO), `--allow-remote` pode atingir dados reais; a trava perde efeito prático |
| SEG-06 | Remover `print` de depuração e registrar em logger com nível | **Implementado (inspeção do código; sem teste dedicado)** |
| SEG-07 | JWT de acesso com expiração configurável; sem refresh token. App mantém sessão offline local por até 24 h | **Parcial.** Expiração do JWT e `SECRET_KEY` ≥ 32 caracteres em produção implementadas (teste SQLite). Sessão offline de 24 h, outbox e novo login online no app: **pendentes** |
| SEG-08 | Upload: validar MIME real JPEG/PNG, tamanho máximo de 15 MB e resolução de conserto | **Parcial.** API implementada (formato real 422, 15 MB 413, conserto 400, `nosniff` em `/static`; teste SQLite). Validação no app e no bucket: **pendente** |
| SEG-09 | Assinatura e fotos acessíveis apenas a quem tem permissão sobre a OS | **Implementado e migrado; não verificado de ponta a ponta.** `/static` removido; assinaturas, fotos, comprovantes e fotos de deslocamento só por rota autenticada com autorização por OS e checagem de que o arquivo pertence à OS (testes SQLite); buckets privados no Supabase real, sem políticas; `testar_storage.py` 6/6 e 17 arquivos migrados e conferidos contra o Supabase real. **Pendentes:** exercitar o painel em navegador; decidir a remoção das cópias locais (`--apagar-locais`); fotos e comprovantes sem cifragem da aplicação (só a da plataforma) |
| SEG-10 | Dados bancários nunca retornados ao técnico que não é admin | **Parcial.** `/auth/me` não devolve dados bancários, CPF/CNPJ nem telefone (teste SQLite); revisão das demais respostas pelo Security pendente. Só o administrador altera dados bancários |
| SEG-11 | Técnico lê apenas clientes das próprias OS | **Implementado (teste SQLite).** Técnico fora das próprias OS → 403 |
| SEG-12 | Chave de serviço do Supabase só no backend. RLS ativado nas tabelas, sem políticas para o papel `anon` | **Verificado no Supabase real (11/11/2026).** `relrowsecurity = true` nas 17 tabelas de `public` e `pg_policies` vazio: `anon`/`authenticated` sem acesso aos dados; a API conecta como dono (BYPASSRLS) e segue funcionando. A chave de serviço permanece só no backend. O risco do projeto compartilhado entre dev e produção continua |
| SEG-13 | App Android guarda token e fila offline em armazenamento seguro. Fotos de clientes ficam só no armazenamento privado do app | **A verificar** o que o app usa hoje (`AsyncStorage` consta nas dependências) |
| SEG-14 | Retenção: sem rotina de exclusão. Bucket privado, backup e acesso mínimo | **Pendente** (depende de SEG-09). Sem rotina de purga nesta versão |
| SEG-15 | Eventos de sincronização rejeitam técnico inativo e OS que não são do técnico | **Implementado no backend (teste SQLite).** Técnico inativo/token inválido → 401 para o lote; OS de outro técnico → `OS_REATRIBUIDA`; arquivo de OS de outro técnico → 403. Não verificado em PostgreSQL |
| SEG-16 | Limitação de tentativas de login (rate limit) | **Pendente** (novo registro na v0.4) |
| SEG-17 | Auditoria de login e de CRUD de clientes/técnicos (PR-20) | **Parcial.** `log_acao` registra ações de OS (atribuição, atualização, desativação com desatribuição). Login e CRUD de cliente/técnico: **pendentes** |
| SEG-18 | Dependências: vulnerabilidades transitivas do Expo no app | **Pendente** (varredura e plano de atualização) |
| SEG-19 | Separação de ambientes dev/produção | **Risco aceito pelo PO (07/11/2026)** com ressalva de SEG: mesmo projeto Supabase nesta fase; reavaliar antes do uso em produção plena |
| SEG-20 | RLS ativado e `REVOKE` para `anon`/`authenticated` nas tabelas `equipamento_modelo` e `os_equipamento` (e sequences); `get_advisors` após a migração | **RLS verificado no Supabase real (11/11/2026)** nas duas tabelas (mesma consulta de SEG-12; sem políticas). A `0007` foi aplicada em 08/11/2026 (ver `backend/migrations/README.md`). O `REVOKE` nas sequences e o `get_advisors` não foram reconferidos nesta verificação; agravado pelo projeto compartilhado dev/produção |
| SEG-21 | Autorização por objeto nos equipamentos: `id_os_equipamento`, `id_servico` e fotos validados contra a OS/visita da URL e contra o técnico atribuído; técnico sem escrita em catálogo/vínculo; sem IDOR | **Implementado (teste SQLite)** — T-43/T-44. Não verificado em PostgreSQL nem revisado pelo Security |
| SEG-22 | Confidencialidade em repouso: campos sensíveis cifrados na aplicação (AES-256-GCM): `visita.documento_cliente`; `tecnico.cpf/cnpj/telefone/banco/agencia/conta/pix` | **Implementado (teste SQLite).** Migrações `0011`/`0012` e cifragem dos dados existentes **aplicadas no Supabase real em 08/11/2026** e conferidas por consulta (0 valores em claro). Adulteração de valor cifrado → erro de decifragem (teste). Padrão de transição seguro (`ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false`; ligar em produção é recusado). **Limite:** AAD por coluna, não por linha (8.1). Não verificado pelo Security nem com a API completa em PostgreSQL |
| SEG-23 | Gestão de chaves: três chaves distintas (dados, índice, selo) em variáveis de ambiente, validadas na inicialização; fora do repositório | **Parcial.** Validação e separação **implementadas e testadas**. **Pendentes:** cofre de segredos/KMS, política de rotação (o prefixo `enc1:` a viabiliza, mas **não há rotina de rotação**), backup da `DATA_ENCRYPTION_KEY` sob responsabilidade do projeto (**perdê-la torna os dados cifrados irrecuperáveis**). A `SUPABASE_SERVICE_KEY` (ignora o RLS e dá acesso total aos buckets) é a credencial mais poderosa do sistema: só no `backend/.env`, fora do Git, do painel e do app; trocar se vazar |
| SEG-24 | Integridade dos arquivos: SHA-256 calculado no aparelho/navegador, conferido e gravado pelo servidor | **Implementado no backend (teste SQLite), painel e app (`tsc` ok, não executados).** Hash na captura persistido na fila; 422 `HASH_DIVERGENTE` com repetição no app; 409 `ARQUIVO_DIVERGENTE`. `SHA256_ORIGEM_OBRIGATORIO=true` adotado porque o app ainda não foi distribuído |
| SEG-25 | Integridade da visita: selo HMAC-SHA256 e verificação administrativa | **Implementado (teste SQLite).** Detecta alteração direta no banco (campo, km, defeito), **remoção do selo** (cópia no `log_acao`) e troca/remoção/adulteração de arquivo em disco. **Corrigido na revisão de 08/11/2026:** o selo acusava `adulterado` em fluxo normal porque incluía pedágio, frete, comprovantes, fotos da ida e o técnico atribuído, que ainda mudam até o fim da volta (agora fora do selo e cobertos por regressão). **Limites:** não cobre volta, `km_total`, custo nem os itens acima; visitas anteriores à v0.6 ficam `sem_selo`; HMAC prova adulteração do banco, **não autoria** (8.1) |
| SEG-26 | Assinatura do cliente cifrada em disco e entregue apenas por rota autenticada | **Implementado (teste SQLite).** `.enc` AES-256-GCM; `/static/assinaturas` inexistente; painel busca como `blob:` com o token. Assinaturas anteriores convertidas e conferidas contra o SHA-256 |
| SEG-27 | TLS obrigatório em todas as conexões: banco, API e app | **Parcial.** Banco: **verificado no ambiente real** — `verify-full` com `DB_SSLROOTCERT=certs/prod-ca-2021.crt` (TLSv1.3, `TLS_AES_256_GCM_SHA384`, 09/11/2026); certificado raiz inexistente recusado e conexão `sslmode=disable` recusada pelo servidor Supabase (`no pg_hba.conf entry ... no encryption`, 11/11/2026). API: cabeçalho HSTS conferido em 11/11/2026 com `ENV=production`, por HTTPS em túnel temporário (Cloudflare); **HTTPS no deploy definitivo (proxy/uvicorn) não verificado**. App: `usesCleartextTraffic=false` por padrão (config resolvida, **build não gerado nem testado**). O bloqueio de `http://` em produção no `api.ts` já existia |
| SEG-28 | Backup e recuperação | **Parcial.** `scripts/backup_banco.py` (export consistente + arquivos + manifesto SHA-256, verificável). **Sem `pg_dump`** nesta máquina (só JSONL); a **restauração nunca foi testada**; o backup contém dados pessoais e fica em `backups/` (ignorado pelo Git) sem criptografia própria |

**Observação (M3):** o CPF mascarado exibido no painel é apenas visual (a proteção em repouso é a cifragem, SEG-22); a regra de armazenamento (máscara canônica do técnico, CPF do cliente só dígitos) está em 4.1, 4.7 e 6.3.1 e não deve ser confundida com proteção de dados.

### 8.1 Confidencialidade e Integridade — decisões e matriz dos quatro pilares (v0.6)

**Ativos:** CPF do cliente, CPF/CNPJ/telefone/dados bancários do técnico, assinatura do cliente, fotos e comprovantes, integridade do registro de atendimento. **Ameaças consideradas:** leitura direta do banco ou de um backup, alteração direta de registro (painel do Supabase, SQL), troca de arquivo em disco, corrupção ou troca de arquivo durante o trânsito ou enquanto espera na fila offline, acesso por URL à assinatura, tráfego sem TLS.

**Decisões criptográficas**

| Finalidade | Algoritmo / modo | Chave | Observações |
|---|---|---|---|
| Campos sensíveis e assinatura em disco | **AES-256-GCM** (biblioteca `cryptography`) | `DATA_ENCRYPTION_KEY` (32 bytes) | Nonce de 96 bits aleatório e novo a cada cifragem; AAD `fast-ariam-v1\|<tabela.coluna>` (assinatura: `arquivo.assinatura`); formato `enc1:<base64(nonce‖ct‖tag)>`; a tag autentica: alteração → `ErroDecifragem` |
| Busca e unicidade de CNPJ | **HMAC-SHA256** determinístico (índice cego) | `INDEX_KEY` | Normaliza para os 14 dígitos; sem a chave não se testam candidatos (CNPJ tem pouca entropia) |
| Integridade de arquivo | **SHA-256** | — (sem chave) | Detecta corrupção e troca acidental; **não autentica quem gerou** o arquivo |
| Integridade da visita | **HMAC-SHA256** sobre JSON canônico (`sort_keys`, separadores compactos, `ensure_ascii=False`, instantes em UTC com microssegundos, valores monetários com 2 casas) | `INTEGRITY_KEY` | Quem altera o banco sem a chave não recalcula o selo. Comparação em tempo constante |
| Senhas | bcrypt | — | Já existente; nunca SHA-256 simples |
| Sessão | JWT **HS256** (simétrico) | `SECRET_KEY` | Ver nota em 6.2 |

**O que o selo cobre e não cobre (D1).** Regra de ouro: **só entra no selo o que o fluxo normal não altera mais depois do fim do atendimento**; do contrário o selo acusaria `adulterado` numa OS legítima. **Cobre**, por visita: ids da OS e da visita, `data_visita`, horários e km da **ida**, início e fim do atendimento, nome e CPF do cliente, URL e SHA-256 da assinatura e, por equipamento, `id_os_equipamento`, `id_equipamento_modelo`, **número de série**, conserto salvo, descrições, defeitos, materiais e fotos de serviço (tipo, URL, hash). **Não cobre** (e por quê): a **volta**, `km_total` e o custo (acontecem depois); **pedágio, frete e comprovantes** (podem chegar até o fim da volta); as **fotos da ida** (podem ser reenviadas até a OS finalizar); o **técnico atribuído** (pode ser desativado e desatribuído entre o atendimento e a volta, RN-08a); e o nome do modelo (renomear reescreve o histórico exibido, 6.13). O que fica fora do selo **não fica sem conferência**: a verificação **re-hasheia em disco** assinatura, fotos de serviço, fotos de deslocamento/odômetro (ida e volta) e comprovantes contra o SHA-256 gravado, e o autor da finalização consta em `log_acao`. **Correção administrativa (RN-49)** de fotos e materiais **resseala** a visita e registra `SELO_RESSELADO` (selo anterior e novo).

**Selo removido (v0.6, revisão).** O selo é gravado **também no `log_acao`** (`ATENDIMENTO_FINALIZADO.selo` e `SELO_RESSELADO.selo_novo`). Se `visita.selo_integridade` for anulado no banco mas o log registra que a visita foi selada, a verificação responde **`adulterado` com `selo_removido`** (e não `sem_selo`). Se o selo da visita for trocado por outro valor, aparece `selo_diverge_da_auditoria`. Só é `sem_selo` (legado) a visita **sem selo e sem selo no log**, isto é, finalizada antes da v0.6. Residual: quem alterar a visita **e** o `log_acao`, e tiver a `INTEGRITY_KEY`, ainda consegue forjar tudo; sem a chave, não.

**Matriz dos quatro pilares**

| Pilar | Controle atual | Evidência | Lacuna / risco residual |
|---|---|---|---|
| **Confidencialidade** | AES-256-GCM nos campos sensíveis e na assinatura; TLS ao banco (`sslmode`), HSTS, Android sem HTTP puro; assinatura só por rota autenticada | Testes SQLite (T-60 a T-69, T-86 a T-89); dados migrados e conferidos por consulta no Supabase | Fotos e comprovantes em **bucket privado** (SEG-09), mas **sem cifragem da aplicação** (só a da plataforma) e com cópia ainda no disco local; sem cofre/rotação de chaves; `sslmode=require` **não valida o certificado** (a aplicação registra aviso em produção; use `verify-full` + CA do provedor); HTTPS do deploy e build Android **não verificados**; backup sem cifragem própria; dev e produção no mesmo projeto; **AAD é por coluna, não por linha**: dá para copiar o valor cifrado do CPF de um técnico para outro e ambos decifram (na visita o selo detecta a troca; em `tecnico` não — amarrar ao `id_tecnico` exigiria gravar em duas etapas e não foi feito) |
| **Autenticação** | Senhas com bcrypt; JWT HS256 com expiração; usuário reconsultado a cada requisição (SEG-01); TLS autentica o servidor **se** o cliente validar o certificado | Já descrito em SEG-01/02/07 | JWT é **simétrico**; sem rate limit de login (SEG-16); sem identidade de dispositivo |
| **Integridade** | SHA-256 de arquivos (origem + servidor), selo HMAC por visita (também registrado no `log_acao`), verificação administrativa, AES-GCM autenticado, `compare_digest` | T-70 a T-85, T-94 a T-99 | Selo parcial (D1); `sem_selo` para o legado; o hash de origem prova que o arquivo não mudou depois da **captura**, não que a foto é verdadeira — e, no aparelho, o SHA-256 e o arquivo ficam **na mesma área do app**: protege de corrupção no trânsito e na fila, **não** de quem tem root no aparelho e altera os dois; atacante com **as duas** chaves e acesso ao banco pode regerar selos |
| **Não repúdio** | **Nenhum controle criptográfico.** A imagem da assinatura é uma imagem; o selo é HMAC (chave do servidor) | — | **Não foi demonstrado não repúdio.** Exigiria assinatura digital assimétrica por signatário (par de chaves no Android Keystore, chave pública cadastrada e revogável) e análise jurídica; **fora do escopo da v0.6** e dependente de decisão do PO. A trilha `log_acao` registra autor, papel e instante, mas não é imutável para quem tem acesso ao banco |

**Ciclo de vida das chaves.** Geração aleatória de 32 bytes (`os.urandom`) em base64; armazenamento em variável de ambiente (`.env`, ignorado pelo Git); as três devem ser diferentes entre si e da `SECRET_KEY` (a aplicação recusa iniciar caso contrário); chaves de teste fixas e distintas ficam apenas em `tests/conftest.py`. **Pendências:** cofre de segredos, rotação (prefixo `enc1:` já reserva a versão), política de revogação e backup da `DATA_ENCRYPTION_KEY` fora do repositório e do banco. Em suspeita de comprometimento: rotacionar, recifrar, regerar `cnpj_idx` e resselar.

**Migração dos dados existentes (08/11/2026).** Ordem executada: backup (`backup_banco.py`, verificado) → `0010` (aditiva) → backup → `0011` (tipos `text`, remoção do CHECK do CPF e do UNIQUE do CNPJ, `cnpj_idx` + índice único) → `cifrar_dados_existentes.py` (dry-run, depois real; 3 técnicos e 2 CPFs de clientes cifrados, `cnpj_idx` preenchido, 2 assinaturas convertidas para `.enc` e conferidas por SHA-256, hashes preenchidos) → `0012` (`cnpj_idx NOT NULL`) → `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false`. Rollback: `0010_rollback`, `0011_rollback` (exige antes `cifrar_dados_existentes.py --decifrar` e **aborta** se houver valor cifrado), `0012_rollback`. Os arquivos `backend/migrations/` (inclusive `0010` a `0012` e os rollbacks) **passam a ser versionados no Git** (decisão do responsável em 08/11/2026; a pasta saiu do `.gitignore`; verificado que não contêm segredos).

**Limitação dos hashes legados.** Os SHA-256 de fotos anteriores à v0.6 foram calculados sobre o arquivo **como estava em 08/11/2026**: servem para detectar alterações **daí em diante**, não provam que eram os originais.

**Evidência e estado.** Todos os controles acima foram exercitados em **SQLite**; no Supabase foram feitas apenas a aplicação das migrações, a conferência por consulta e a leitura somente-leitura descrita no cabeçalho. Nenhum SEG-22 a SEG-28 está *verificado*.

## 9. Armazenamento de arquivos — Supabase Storage privado

**Situação atual:** confirmado pelo responsável do projeto: fotos, comprovantes e assinaturas estão armazenados no disco do servidor (`static/uploads/`, `static/assinaturas/`). Esse armazenamento local não é adequado como destino persistente em ambiente gerenciado e deve ser migrado.

> **Status em 09/11/2026 (v0.6): IMPLEMENTADO e MIGRADO para o Supabase real; painel não exercitado em navegador.** Os buckets privados `fast-ariam-privado` e `fast-ariam-privado-dev` existem no Supabase real (migração `0013_storage_buckets`, aplicada pelo MCP em 08/11/2026): `public = false`, limite 15 MB, tipos `image/jpeg`, `image/png` e `application/octet-stream` (assinaturas `.enc`), RLS ativo em `storage.objects` e **nenhuma política** (acesso de `anon`/`authenticated` negado). `scripts/testar_storage.py` passou **6/6 contra o Supabase real** (upload, download idêntico, recusa de sobrescrita, link público negado, leitura sem credencial negada, remoção). `scripts/migrar_arquivos_para_storage.py` migrou **17 arquivos (15 fotos + 2 assinaturas `.enc`) em 09/11/2026**, cada um conferido byte a byte após o upload; uma nova simulação mostra 17 `ja_no_bucket` e a leitura de ponta a ponta pelo backend (via Supabase) devolve as 17 referências com o SHA-256 do banco conferindo. Os **5 arquivos órfãos** (sem referência no banco; nomes de uma versão antiga: `servico_1_foto_conserto_*`, `visita_1_*`) **foram excluídos do disco local** depois de confirmados, com hash idêntico, nos backups `20261108-221733` e `20261108-224357`; não foram enviados ao bucket. As **cópias locais dos 17 arquivos migrados continuam no disco** (não foi usado `--apagar-locais`). **Não verificado:** o painel com `FotoSegura` e `AssinaturaImagem` não foi aberto em navegador; as rotas `arquivos/conteudo` e `assinatura` só foram exercitadas por teste automatizado.

> **Registro operacional (09/11/2026) — incidente na validação.** Ao colocar a chave de serviço no `.env`, a suíte de testes passou a herdar `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (o `conftest.py` isolava o banco, mas não o Storage) e **gravou cerca de 503 objetos de teste no bucket real** (520 no total contra 17 legítimos). O banco **não** foi afetado (já era isolado em SQLite). Correção: `conftest.py` agora zera `SUPABASE_*` e **aborta a sessão** se o armazenamento não for local; a suíte voltou a rodar em 1m46 e uma execução posterior confirmou que não gravou nada novo no bucket. **Limpeza concluída em 09/11/2026, com autorização expressa do responsável:** foram removidos, pela API do Storage, os **503 objetos** que o banco real não referenciava (o script de apoio, descartável e fora do repositório, abortaria se algum dos 17 legítimos faltasse). Depois: o bucket tem **17 objetos** (15 em `uploads`, 2 em `assinaturas`, mesmos tamanhos de antes da suíte), conferido por consulta ao `storage.objects`, e a leitura de ponta a ponta pelo backend devolve **17/17** referências com o SHA-256 do banco conferindo. Lição: toda nova credencial/serviço externo precisa ser neutralizada no `conftest.py` **antes** de entrar no `.env`.

> **Atualização v0.6:** as **assinaturas** já são gravadas **cifradas** e servidas por rota autenticada (SEG-26). Fotos e comprovantes continuam em `static/uploads` e **públicos**. Ao migrar para o Storage: calcular o checksum dos arquivos já cifrados/decifrados conforme o caso (a assinatura `.enc` deve ser decifrada em memória, conferida contra `assinatura_sha256` e recifrada no destino, ou mantida cifrada no bucket), preservar `sha256` e não alterar `selo_integridade`.

**Como ficou o desenho (v0.6)**

- **A referência no banco não mudou.** As colunas `url` continuam com `/static/uploads/<nome>` e `/static/assinaturas/<nome>.enc`; é um identificador lógico, **não** um endereço (o `/static` foi removido). O objeto vai para `uploads/<nome>` e `assinaturas/<nome>` dentro do bucket. Assim **nenhuma linha é atualizada na migração e os selos de integridade, que incluem essas referências, continuam válidos**.
- **Leitura somente por rota autenticada da API**, que confere a permissão do usuário sobre a OS e que o arquivo pertence **àquela** OS (nome adivinhado de outra OS → 404): `GET /api/chamados/{id}/arquivos/conteudo?url=<referência>` (fotos de serviço, comprovantes e fotos de odômetro/deslocamento; `Cache-Control: private, max-age=300`) e `GET /api/chamados/{id}/visitas/{v}/assinatura`. O painel busca com o token e exibe por `blob:` (`FotoSegura`, `AssinaturaImagem`). A API **faz o proxy** do arquivo em vez de emitir links assinados do Supabase: mesmo caminho de código em dev/teste/produção, nenhuma URL com token circula e o painel não depende de CORS do Storage; a desvantagem é o tráfego passar pelo backend (aceitável para imagens de até 15 MB neste volume). Links assinados (`createSignedUrl`) ficam como evolução, se o egress do backend virar problema.
- **Escrita sem sobrescrita** (`x-upsert: false`): nome repetido é erro. Falha do Storage vira **503** sem expor a chave nem o corpo enviado.
- **Formato da chave:** a chave nova `sb_secret_...` **não é JWT** e vai **somente** no cabeçalho `apikey` (no `Authorization: Bearer` a plataforma a rejeita com `Invalid Compact JWS`); a chave antiga `service_role` (JWT) vai nos dois. O cliente escolhe pelo prefixo `sb_` (teste). Recomenda-se a chave nova (rotação sem derrubar a JWT secret).
- **Chave de serviço** só em `backend/.env` (`SUPABASE_SERVICE_KEY`); `SUPABASE_URL` e a chave devem ser definidas **juntas**; em `ENV=production` o Supabase é obrigatório (disco local é efêmero e não privado); sem as variáveis, dev/teste usam o disco local.
- **Cifragem:** as assinaturas já sobem cifradas pela aplicação (AES-256-GCM). Fotos e comprovantes ficam com a cifragem em repouso da plataforma Supabase; cifrá-los também na aplicação é uma evolução possível, **não feita**.
- **Dev x produção:** o projeto é compartilhado; use `STORAGE_BUCKET=fast-ariam-privado-dev` fora de produção.

**Destino definido (SDD original):** Supabase Storage em bucket privado `fast-ariam-privado`.

| Item | Especificação |
|---|---|
| Bucket | `fast-ariam-privado`, privado (não público) |
| Plano inicial | Pode iniciar no plano Free, desde que dentro das cotas e limitações operacionais; não é necessário plano pago apenas para criar bucket privado |
| Cota Free atualmente documentada | 1 GB de armazenamento; 5 GB de egress não cacheado e 5 GB cacheado |
| Limite máximo de arquivo no projeto Free | 50 MB; configurar o bucket e a aplicação para o limite menor, de 15 MB |
| Upload permitido | JPEG/PNG; limite de 15 MB por imagem |
| Caminho | **Implementado como `uploads/<nome>` e `assinaturas/<nome>`** (o nome já carrega `chamado_{id}_visita_{id}_...`). A estrutura `chamados/{id_os}/visitas/{id_visita}/{categoria}/...` do desenho original **não foi adotada** (exigiria renomear objetos e as referências, e invalidaria os selos) |
| Categorias | `odometro`, `deslocamento`, `defeito`, `conserto`, `comprovante`, `assinatura` |
| Acesso | Bucket privado; somente backend com `SUPABASE_SERVICE_KEY` faz operações privilegiadas. API verifica permissão e gera URL assinada de curta duração (ex.: 1 hora) |
| Colunas | Manter colunas `*_url`/`url` como referência ao path do objeto, não URL pública permanente |
| Migração | **Executada em 09/11/2026:** `scripts/migrar_arquivos_para_storage.py` (idempotente; `--dry-run`; confere o SHA-256 do banco antes de subir, **nunca sobrescreve**, baixa e compara byte a byte depois de subir, não sobe assinatura em claro, relata ausentes/órfãos/divergentes/conflitos; `--apagar-locais` só apaga o que foi confirmado no bucket). Resultado: 17 migrados, 0 conflitos, 0 divergentes, 0 ausentes, 5 órfãos (excluídos do disco, ver acima). Como a referência não muda, não houve atualização de linhas |

**Limitações financeiras/operacionais:** a cota de 1 GB e o egress do plano Free não são ilimitados. A documentação atual informa que projetos Free podem ser pausados após uma semana de inatividade. Para operação de produção que exija disponibilidade contínua, maior volume, backup/SLA ou cotas superiores, avaliar o plano Pro antes do lançamento. O custo do plano deve ser validado no momento da contratação.

**Segurança:** não usar bucket público. Não expor `SUPABASE_SERVICE_KEY` ao painel ou aplicativo. Não devolver URL permanente pública. As URLs assinadas devem ser emitidas somente após verificar o vínculo do usuário com a OS. Os arquivos permanecem privados, sem rotina de exclusão automática nesta versão.

**Fontes oficiais consultadas em 29/10/2026:** [Storage Pricing](https://supabase.com/docs/guides/storage/pricing), [Billing on Supabase](https://supabase.com/docs/guides/platform/billing-on-supabase), [Bucket Fundamentals](https://supabase.com/docs/guides/storage/buckets/fundamentals) e [File Upload Limits](https://supabase.com/docs/guides/storage/uploads/file-limits). A SDD mantém esses números como cotas a monitorar, pois podem mudar conforme o fornecedor.

## 10. Erros esperados e mensagens

| Caso | Código | Mensagem atual | Ação |
|---|---|---|---|
| Login inválido | 401 | "Email ou senha incorretos" | OK |
| Técnico inativo tenta login | 401 | "Email ou senha incorretos" | Implementado (SEG-02); mesma mensagem para e-mail inexistente, senha errada e usuário inativo |
| Acesso a OS de outro técnico | 403 | "Acesso negado a este chamado." | OK |
| Iniciar deslocamento de ida duas vezes | 400 | "Deslocamento de ida já iniciado" | OK |
| Volta sem fim do atendimento | 400 | "Finalize o atendimento antes de iniciar o deslocamento de volta" | OK |
| Finalizar atendimento com pausa ativa | 400 | "Não é possível finalizar o atendimento enquanto a OS estiver pausada." | OK |
| Upload com hash diferente do calculado no servidor | 422 | "Arquivo corrompido em trânsito (hash divergente)." `codigo: HASH_DIVERGENTE` | Implementado (v0.6); o app repete o envio |
| Hash ausente com `SHA256_ORIGEM_OBRIGATORIO=true` | 422 | "Informe o SHA-256 do arquivo (campo 'sha256')." `codigo: HASH_AUSENTE` | Implementado (v0.6) |
| Hash fora do formato (64 hex) | 422 | "SHA-256 inválido: envie 64 caracteres hexadecimais." `codigo: HASH_INVALIDO` | Implementado (v0.6) |
| Mesmo `client_file_id` com conteúdo diferente | 409 | "client_file_id já usado com outro conteúdo." `codigo: ARQUIVO_DIVERGENTE` | Implementado (v0.6) |
| `GET .../assinatura` de visita sem assinatura ou sem arquivo | 404 | "Esta visita não tem assinatura." / "Arquivo da assinatura não encontrado." | Implementado (v0.6) |
| Assinatura `.enc` adulterada | 500 | "Assinatura ilegível: falha de integridade. Avise o administrador." | Implementado (v0.6); registra erro no log |
| `verificar-integridade` por não admin / sem token | 403 / 401 | Mensagens padrão de autorização | Implementado (v0.6) |
| Transição inválida de status | 409 | `detail` explica a transição | Implementado (TR-01) |
| Enum de status inválido | 422 | Lista de valores aceitos | OK, mas o painel envia valor inválido (PR-07) |
| Pausa com motivo fora da lista | 422 | — | Adicionar (seção 7) |
| Pausa "Outro" sem descrição | 422 | — | Adicionar |
| Cancelar sem motivo | 422 | — | Adicionar |
| Reagendar em status não permitido | 409 | — | Adicionar, com o status atual na mensagem (6.10) |
| CPF inválido na assinatura | 422 | — | Adicionar: "CPF inválido" |
| Foto de conserto abaixo de 960×1280 | 400 | "Resolução insuficiente..." | OK. Remover para foto de defeito (PR-29) |
| Evento de sincronização rejeitado | 200, `resultado: rejeitado` | — | Adicionar, com `codigo` (6.12) |
| Conflito administrativo na sincronização | 200 por evento + OS `Pendente` | — | Registrar `CONFLITO_ADMINISTRATIVO`, remover atribuição e auditar |
| Imagem acima de 15 MB | 413 | Mensagem de limite de tamanho | Implementado na API: aborta a leitura e não persiste arquivo parcial |
| Técnico inativo no sincronismo | 401 | — | Adicionar (SEG-01, SEG-15) |
| Imagem que não é JPEG/PNG real ou arquivo vazio | 422 | "Formato não permitido..." / "Arquivo de imagem vazio." | Implementado |
| Upload em OS `Finalizado` | 409 | "OS 'Finalizado' não aceita novos arquivos." | Implementado |
| `finalizar-dados` | 410 | Endpoint descontinuado | Implementado; usar `finalizar-atendimento` |
| `POST .../visitas` com visita não finalizada existente | 409 | "A OS já possui uma visita aberta..." | Implementado (TR-10) |
| `ocorrido_em` sem fuso ou > 5 min no futuro | 422 | Mensagem pede conferir relógio/fuso | Implementado (6.6.4) |
| Reagendar com data passada | 422 | "A data do reagendamento não pode estar no passado." | Implementado |
| Reagendar sem técnico ativo | 409 | Mensagem informa o motivo | Implementado |
| `PATCH` da OS por técnico | 403 | "Técnicos não podem alterar a OS por PATCH..." | Implementado |
| `PATCH` com `status: Finalizado` | 403 | OS só finaliza na volta | Implementado (T-04) |
| Atribuir OS a usuário que não é técnico (admin) | 400 | "...não é um técnico e não pode receber OS." | Implementado (TR-11) |
| Criar OS sem equipamento *(v0.5)* | 422 | — | Adicionar (RN-41) |
| Modelo duplicado no catálogo *(v0.5)* | 409 | — | Adicionar (RN-40) |
| Vincular modelo inativo ou série vazia *(v0.5)* | 422 | — | Adicionar |
| Série repetida na mesma OS *(v0.5)* | 409 | — | Adicionar (RN-41) |
| Técnico escreve no catálogo ou no vínculo *(v0.5)* | 403 | — | Adicionar (RN-42) |
| Técnico envia série/nome/equipamento em serviço *(v0.5)* | 422 | — | Adicionar |
| `POST .../servicos` *(v0.5)* | 410 | Endpoint descontinuado | Adicionar |
| `id_os_equipamento`/`id_servico` de outra OS ou visita *(v0.5)* | 404 | — | Adicionar (SEG-21) |
| Iniciar atendimento sem foto de defeito (ou OS sem equipamento) *(v0.5)* | 409 | "Não é possível iniciar o atendimento sem foto do defeito de cada equipamento. Pendentes: ..." | Adicionar (TR-12) |
| Finalizar atendimento sem conserto salvo ou sem foto de conserto *(v0.5)* | 409 | "Não é possível finalizar o atendimento sem salvar o conserto e a foto do conserto de cada equipamento. Pendentes: ..." | Adicionar (TR-13) |
| Salvar conserto sem defeito principal *(v0.5)* | 422 | — | Adicionar (RN-47) |
| Alterar/remover equipamento após o início do atendimento, com conteúdo registrado, ou remover o último *(v0.5)* | 409 | — | Adicionar (RN-45) |
| Foto de conserto antes de iniciar, ou foto de serviço do técnico após finalizar *(v0.5)* | 409 | — | Adicionar (PR-42) |
| Atribuir, reagendar ou iniciar atendimento em OS legada sem equipamento *(v0.5)* | 409 | "OS sem equipamento vinculado" | Adicionar (TR-15, RN-46) |
| Correção de foto/material fora de OS Finalizada ou em OS cancelada, ou por técnico *(v0.5)* | 409 / 403 | — | Adicionar (RN-49) |
| Remover a última foto de defeito/conserto de um equipamento, ou enviar campo diferente de `materiais_utilizados` na correção *(v0.5)* | 409 / 422 | — | Adicionar (RN-49) |
| Alterar modelo/série de equipamento em OS Finalizada *(v0.5)* | 409 | — | Adicionar (RN-49) |

## 11. Critérios de aceite técnicos (testes)

Cada teste descreve Dado / Quando / Então e deve virar teste automatizado (`backend/tests/`).

**T-01 Fluxo normal completo**
- Dado OS Agendado para o técnico T, com cliente ativo
- Quando T chama: iniciar-deslocamento ida → upload odômetro → finalizar ida → **(v0.5) upload da foto de defeito de cada equipamento da OS** → iniciar atendimento → preencher defeitos/materiais → **(v0.5) salvar-conserto** e upload da foto de conserto de cada equipamento → finalizar-atendimento (assinatura) → iniciar volta → finalizar volta
- *(v0.5: o fluxo antigo "iniciar atendimento → registrar serviço com série e nome → fotos" não é mais válido; o helper `Fluxo` dos testes precisa criar modelo, vínculo e as fotos antes de iniciar.)*
- Então OS = `Finalizado`, `data_conclusao` = hoje, `servico_finalizado` = true, custo calculado sem IDs zerados (PR-12).

**T-02 Pausa e reagendamento**
- Dado visita em atendimento
- Quando T chama pausar com motivo "Peça pendente" e depois finalizar volta
- Então OS = `Aguardando Reagendamento`, pausa ativa, e `finalizar-atendimento` retorna 400 enquanto pausada.
- Quando admin chama reagendar com nova data
- Então OS = `Agendado`, pausa com `is_ativa = false`, nova visita criada.

**T-03 Permissão cruzada**
- Dado OS atribuída a T1
- Quando T2 chama GET, PATCH ou iniciar-deslocamento na OS
- Então todas retornam 403.

**T-04 Técnico não finaliza OS diretamente**
- Dado OS em atendimento
- Quando T chama `PATCH /api/chamados/{id}` com `status: "Finalizado"`
- Então recebe 403.
- E `POST /api/chamados/{id}/concluir` não existe mais (404 ou 405). O administrador também recebe 403 ao enviar `status: "Finalizado"` por `PATCH`; qualquer outro `status` diferente da transição implícita da atribuição recebe 409. O técnico recebe 403 em qualquer `PATCH` da OS.

**T-05 Desativação efetiva**
- Dado técnico T com token válido
- Quando admin desativa T e T usa o mesmo token
- Então recebe 401.

**T-06 Atribuição pelo painel**
- Dado OS `Pendente` sem técnico
- Quando admin envia `PATCH` com `id_tecnico_atribuido` (sem `status`)
- Então HTTP 200 e OS = `Agendado`. **(Hoje falha por PR-07 se o painel enviar `AGENDADO`.)**

**T-07 Validação de comprovante**
- Dado visita com `valor_pedagio = 9.80` e sem comprovante
- Quando T finaliza a visita (`servico_finalizado: true`)
- Então HTTP 400 com a mensagem de comprovante obrigatório.

**T-08 Resolução de foto**
- Dada imagem 800 × 600
- Quando T envia como `conserto`
- Então HTTP 400 com "Resolução insuficiente".
- Quando T envia a mesma imagem como `defeito`
- Então HTTP 200 (a regra vale só para conserto, PR-29).
- Dadas imagens 960 × 1280 e 1280 × 960 enviadas como `conserto`, então HTTP 200 (qualquer orientação).
- Dadas imagens 1000 × 1200 (maior lado < 1280) e 900 × 1500 (menor lado < 960) enviadas como `conserto`, então HTTP 400.

**T-09 Painel sem dados fictícios**
- Dado API fora do ar
- Quando admin abre a lista de técnicos
- Então o painel mostra erro e lista vazia, sem nenhum registro gerado no cliente (PR-02).

**T-10 Listagem com visita incompleta**
- Dado visita criada com `servico_finalizado: false` e horários nulos
- Quando admin lista as OS
- Então HTTP 200 (não 500). Ver PR-11.

**T-11 Pausa pelo administrador**
- Dado visita em atendimento
- Quando admin chama `pausar` com `motivo: "Outro"` e sem `descricao`
- Então HTTP 422. Com `descricao`, HTTP 200, `por_papel = "admin"` e OS = `Pausado`.

**T-12 Motivo fora da lista**
- Quando alguém envia `motivo: "Almoço"`
- Então HTTP 422.

**T-13 Reagendamento por status**
- Dado OS em cada status da tabela 6.10
- Quando admin reagenda
- Então o resultado de cada linha da tabela (200 ou 409) é o esperado. Em `Pausado`, a API retorna 409. Ao finalizar a volta, a OS vai para `Aguardando Reagendamento`; somente após o admin reagendar é criada nova visita e a OS vai para `Agendado` (TR-05).

**T-14 Cancelamento com motivo**
- Dado OS Em Atendimento
- Quando admin chama `cancelar` sem `motivo`
- Então HTTP 422. Com `motivo`, HTTP 200 e `motivo_cancelamento`, `cancelado_em` e `cancelado_por` preenchidos. Para OS Finalizada, HTTP 409.

**T-15 CPF**
- Dado `documento_cliente = "111.111.111-11"`
- Quando T finaliza o atendimento
- Então HTTP 422. Com CPF válido, a visita grava os 11 dígitos.

**T-16 Várias visitas e assinatura**
- Dada OS com duas visitas finalizadas
- Então cada visita tem a própria `assinatura_url`, e a segunda não sobrescreve a primeira (PR-35).

**T-17 Desativação de técnico (RN-08a)**
- Dado técnico T com token válido e OS atribuídas nos status Agendado, Em Atendimento, Pausado e Aguardando Reagendamento, mais uma OS Finalizada e uma OS cancelada
- Quando admin desativa T (`DELETE /api/tecnicos/{id}`) e T tenta usar o mesmo token
- Então a requisição seguinte de T retorna 401.
- E as quatro OS não finalizadas e não canceladas passam a `Pendente` com `id_tecnico_atribuido` NULL, na mesma transação da desativação.
- E visitas, fotos, serviços e pausas dessas OS continuam existindo (pausas ativas ficam com `is_ativa = false`).
- E a OS Finalizada e a OS cancelada permanecem inalteradas.
- E existe um registro `DESATRIBUIDA_POR_DESATIVACAO` em `log_acao` por OS afetada.
- Quando o admin atribui uma dessas OS a outro técnico ativo, então a OS vai a `Agendado`, a visita iniciada por T permanece como histórico e existe uma visita nova para o novo técnico (RN-11a).

**T-18 Sincronização idempotente** *(implementado no backend: `test_t18_reenviar_o_mesmo_lote_e_idempotente`)*
- Dado um lote de 5 eventos
- Quando o mesmo lote é enviado duas vezes
- Então a segunda resposta traz `duplicado` para todos e o banco não tem registros repetidos.

**T-19 Horário do aparelho** *(implementado no backend: fluxo completo offline e SY-04)*
- Dado evento com `ocorrido_em` 3 horas antes do envio
- Então a visita grava o horário do evento, não o do recebimento (AR-05).

**T-20 Conflito com ação do admin** *(implementado no backend: equipamento removido e pausa feita pelo administrador)*
- Dado técnico offline e admin que pausa/reatribui a OS durante o período offline
- Quando o técnico sincroniza eventos incompatíveis com a alteração administrativa
- Então os eventos conflitantes são rejeitados com `CONFLITO_ADMINISTRATIVO`, a OS não finalizada passa para `Pendente`, fica sem técnico e o conflito é auditado (SY-05). Eventos compatíveis anteriores podem ser aplicados conforme `ocorrido_em`.

**T-21 Conclusão pela volta**
- Dada visita sem pausa ativa
- Quando T finaliza a volta
- Então a OS é `Finalizado`, com cálculo de custo congelado em `custo_os`.

**T-22 Custo global e snapshot**
- Dada configuração global de custo
- Quando OS de técnicos diferentes são calculadas
- Então ambas usam os mesmos valores globais. O técnico não possui endpoint nem tela para alterar parâmetros. Ao finalizar, o custo e os valores utilizados são congelados em `custo_os`.

**T-23 Cliente sem código**
- Quando admin cria cliente sem `codigo`
- Então HTTP 422 (e não 500, PR-27).

**T-24 Limite de imagem**
- Dado arquivo de imagem JPEG/PNG de 15 MB ou menos
- Quando o técnico envia imagem que cumpre resolução/validações aplicáveis
- Então o upload é aceito. Arquivo acima de 15 MB recebe erro padronizado sem persistir arquivo parcial.

**T-25 Sessão offline por 24 horas**
- Dado técnico autenticado online e app com sessão segura local
- Quando fica sem internet por até 24 horas
- Então consegue registrar operações dentro do limite. Não há refresh token. Após 24 horas, novas operações autenticadas são bloqueadas até login online, e a outbox é preservada.

**T-26 OS Pendente sem técnico**
- Quando admin cria OS sem técnico
- Então status é `Pendente` e `id_tecnico_atribuido` é NULL. Ao atribuir técnico ativo, passa para `Agendado`. `Aberto` não é persistido em novas operações.

**T-27 Metas de desempenho**
- Em homologação com até 20 usuários simultâneos e 1.000 OS consultáveis, listagens/detalhes atingem p95 ≤ 2 s.
- Em rede de referência com upload estável de 10 Mbps, imagem de 15 MB conclui em até 30 s.

**T-28 Visita automática (RN-11a)**
- Quando admin cria OS com técnico ativo e `data_agendamento` informada, então existe uma visita aberta com `data_visita` igual a `data_agendamento`.
- Quando admin cria OS com técnico sem `data_agendamento`, então `data_visita` é a data de hoje em America/Sao_Paulo.
- Quando admin atribui técnico a OS `Pendente`, então a visita aberta existe ao fim da mesma transação.
- Quando se chama `POST .../visitas` e já existe visita não finalizada, então HTTP 409.

**T-29 Administrador não recebe OS (TR-11)**
- Quando admin cria ou atualiza OS com `id_tecnico_atribuido` de um usuário `admin`, então a operação é recusada (400) e nada é alterado.

**T-30 CPF e CNPJ do técnico**
- Quando admin cria técnico com CPF e CNPJ só com dígitos, então são gravados e devolvidos como `000.000.000-00` (14) e `00.000.000/0000-00` (18).
- Dado `documento_cliente` válido na assinatura, então a visita grava 11 dígitos, sem máscara.

**T-31 Custo de visita pausada**
- Dada visita pausada com tempo de atendimento registrado, então o tempo de serviço contribui com zero para o custo; deslocamento, km, pedágio, frete e materiais continuam considerados.

**T-32 `ocorrido_em`**
- Dado `ocorrido_em` com fuso, até 5 minutos no futuro ou no passado, então a ação é aceita e o instante é o informado.
- Dado `ocorrido_em` sem fuso ou mais de 5 minutos no futuro, então HTTP 422. Omitido, o servidor usa o instante atual.

**T-33 Contrato de `Visita` e `finalizar-dados`**
- Então a resposta de visita inclui `assinatura_url`, `nome_cliente_assinatura`, `documento_cliente`, os seis `*_em` e `pausas[]` com `id_pausa`, `visita_id`, `motivo`, `descricao`, `criado_em`, `encerrada_em`, `is_ativa`, `por_usuario_id` e `por_papel`.
- E `POST .../finalizar-dados` retorna 410.

**T-34 Reagendamento: data e técnico**
- Quando admin reagenda com data no passado, então HTTP 422. Quando a OS não tem técnico ativo, então HTTP 409.

**T-35 Uploads: OS finalizada, tamanho e formato**
- Quando o **técnico** envia arquivo a OS `Finalizado`, então HTTP 409 (v0.5: a correção de foto pelo **administrador** em OS Finalizada é permitida, ver T-58). Imagem acima de 15 MB: HTTP 413. Arquivo que não é JPEG/PNG real: HTTP 422.

**T-36 Custos congelados**
- Dada OS finalizada, então `GET .../custos` devolve `congelado = true`, `calculado_em` e `valores_utilizados`, e o resultado não muda após alteração da configuração global.

### 11.1 Testes da regra de equipamento (v0.5)

**Plano, não resultado: nada foi executado.** Todos os testes atuais rodam em SQLite; unicidade sem diferenciar maiúsculas, índices funcionais, FK/`ON DELETE`, CHECK, triggers, `SELECT ... FOR UPDATE` e concorrência (T-55) precisam ser verificados em PostgreSQL/Supabase antes de qualquer item ser dado como aprovado.

**T-37 Catálogo**
- Admin cria modelo "Freezer vertical modelo X": 201. Técnico: 403. Sem nome ou só espaços: 422. Técnico não consegue ler `/api/equipamentos` (403).

**T-38 Modelo duplicado**
- "Freezer Vertical Modelo X" e " freezer vertical modelo x " após o modelo acima: 409 (sem diferenciar maiúsculas e espaços nas pontas).

**T-39 Desativar modelo em uso**
- Dado modelo vinculado a uma OS. Quando o admin o desativa (`DELETE`), então 204, a OS existente mantém o vínculo e o histórico; vincular o modelo inativo a uma OS nova: 422. Reativar (`PATCH is_active`) volta a permitir.

**T-40 OS exige equipamento**
- `POST /api/chamados/` com `equipamentos` ausente ou vazio: 422 e nada criado (nem OS nem visita). Modelo inexistente: 404/422; inativo: 422. A validação de equipamento não pode mascarar T-29 (admin como técnico atribuído).

**T-41 Vários equipamentos**
- OS com 3 equipamentos, dois do mesmo modelo com séries diferentes: 201; `Chamado.equipamentos` traz os 3; a visita automática tem 3 registros de serviço.

**T-42 Série duplicada**
- Mesma série na mesma OS (inclusive "ab-1" vs "AB-1" e com espaços): 409/422 e nada gravado (atômico). A mesma série em outra OS é aceita.

**T-43 Técnico não edita equipamento**
- Técnico faz POST/PATCH/DELETE em `/api/equipamentos` e em `/api/chamados/{id}/equipamentos`: 403. Técnico envia `numero_serie_atendido` ou `nome_equipamento` em `PATCH .../servicos/{s}`: 422 e o valor no banco não muda. `POST .../servicos`: 410.

**T-44 Permissão cruzada e IDOR**
- T2 lê equipamentos, sobe foto ou salva serviço de OS do T1: 403. `id_servico` de outra visita/OS na URL: 404. Técnico inativo: 401.

**T-45 Iniciar atendimento sem foto de defeito**
- Dada OS com 2 equipamentos e ida finalizada. Quando T inicia com foto em apenas 1: 409 listando o pendente; OS continua `Agendado` e `atendimento_inicio_em` nulo; `GET .../estado` lista a pendência e `pode_iniciar_atendimento = false`. Com foto nos dois: 200 e OS = `Em Atendimento`.

**T-46 Foto de defeito: limites**
- 800 × 600 é aceita como defeito (CA-14). Upload recusado (413/422) não conta. A foto do equipamento A não vale para B. Foto de conserto não vale como defeito.

**T-47 Finalizar sem conserto salvo**
- Atendimento iniciado, registro de serviço criado só pela foto de defeito, sem `salvar-conserto`: `finalizar-atendimento` retorna 409 e **nenhuma** assinatura, nome ou CPF é gravada.

**T-48 Finalizar sem foto de conserto**
- 1 de 2 equipamentos sem foto de conserto: 409. Com as duas fotos e os dois consertos salvos: 200 e `assinatura_url` preenchida.

**T-49 Resolução do conserto**
- 800 × 600, 1000 × 1200 e 900 × 1500 como conserto: 400. 960 × 1280 e 1280 × 960: 200 (T-08).

**T-50 Salvar conserto**
- Sem defeito principal: 422. Antes de iniciar o atendimento ou com pausa ativa: 400. Repetir: idempotente (mantém a primeira marca).

**T-51 Pausa × exigências**
- Pausar com conserto pendente é permitido. `finalizar-atendimento` pausado: 400 (a checagem de pausa vem antes das travas). Finalizar a volta pausada leva a OS a `Aguardando Reagendamento` sem exigir conserto nem foto de conserto.

**T-52 Multi-visita**
- Após reagendar, a visita 2 tem novos registros de serviço; iniciar o atendimento sem a foto de defeito **da visita 2** retorna 409 mesmo que a visita 1 tenha as fotos. A assinatura da visita 1 permanece (CA-13).

**T-53 OS Finalizada ou cancelada**
- Vincular, editar ou remover equipamento em OS Finalizada ou cancelada: 409 (inclusive modelo/série em OS Finalizada, RN-49). Foto de serviço enviada pelo técnico: 409. A correção de fotos/materiais pelo administrador em OS Finalizada segue T-58.

**T-54 Admin edita equipamento (RN-45)**
- Antes do início do atendimento: PATCH da série aceito e auditado em `log_acao` (`OS_EQUIPAMENTO_ALTERADO`). Depois: 409. Remoção com foto/defeito/conserto registrado: 409; sem conteúdo: 204 (e o registro de serviço vazio some). Remover o último equipamento: 409. Vincular novo equipamento com visita aberta cria o registro de serviço correspondente e o `estado` é recalculado.

**T-55 Concorrência**
- Admin remove/vincula equipamento enquanto o técnico inicia ou finaliza o atendimento (execuções simultâneas em PostgreSQL): nenhum estado inconsistente (travas com `FOR UPDATE`).

**T-56 Offline (backend implementado; `backend/tests/chamados/test_sync.py`, 15 testes em SQLite)**
- `atendimento_iniciado` sem foto de defeito aplicada: `rejeitado` com `FOTO_DEFEITO_AUSENTE`; a foto chegando depois e o evento reenviado com novo `client_event_id` resultam em `aplicado`. `atendimento_finalizado` sem conserto/foto: `CONSERTO_INCOMPLETO`. Equipamento removido pelo admin durante o período offline: `CONFLITO_ADMINISTRATIVO` com arquivos preservados.

**T-57 Migração e legado (4.9)**
- Upgrade e downgrade em banco limpo e em cópia com dados reais; idempotência (rodar duas vezes); OS Finalizadas, assinaturas e custo congelado idênticos (contagens e checksums); zero fotos órfãs; série duplicada na mesma OS não aborta a migração (vai ao relatório); OS legada sem equipamento: atendimento bloqueado (CA-35).

**T-58 Correção administrativa de OS Finalizada (RN-49)**
- Dada OS `Finalizado`. Admin envia nova foto de conserto (≥ 960 × 1280) a um equipamento: 200 e `log_acao` `FOTO_CORRIGIDA_ADMIN`. Admin remove uma das duas fotos de conserto: 204; remove a **última** foto de defeito ou de conserto do equipamento: 409. Admin corrige `materiais_utilizados`: 200 e `MATERIAIS_CORRIGIDOS_ADMIN` com antes/depois; PATCH com qualquer outro campo: 422.
- Após corrigir materiais, `GET .../custos` devolve `congelado = true` com o **novo total** (recalculado com os `valores_utilizados` do snapshot, mesmo que a configuração global tenha mudado desde a finalização) e `log_acao` guarda total anterior e novo; corrigir só fotos não altera o custo. A OS permanece `Finalizado`; assinatura, km e horários não mudam.
- Técnico tenta qualquer dessas correções: 403/409. Admin tenta corrigir OS que **não** está Finalizada (ex.: `Em Atendimento`) ou OS cancelada: 409. Admin tenta alterar modelo/série em OS Finalizada: 409.

**T-59 OS sempre com equipamento (RN-41, RN-46, TR-15)**
- Criar OS sem equipamento: 422 (T-40). Remover o último equipamento: 409. OS legada sem equipamento: atribuir técnico, reagendar e iniciar atendimento retornam 409 "OS sem equipamento vinculado"; após o admin vincular um equipamento, as três operações funcionam.

**Regressões esperadas nos testes existentes (atualizar antes de usar como oráculo)**
- `Fluxo.criar_os` sem equipamentos passa a retornar 422 em toda a suíte; o helper deve criar modelo e vínculo.
- `Fluxo.ate_em_atendimento`/`iniciar_atendimento` quebram sem a foto de defeito (afeta T-01/T-21, T-02, T-07, T-11, T-12, T-15, T-31, RN-26 e custos).
- `Fluxo.servico` envia série e nome pelo técnico: quebra (`test_servicos_e_robustez`, `test_permissoes`, `test_uploads`, `test_visita_aberta_e_correcoes_qa`, `scripts/smoke_api.py`; no app `registroEquipamento.tsx` e `api/servico.ts`).
- T-08 e T-24 usam `/servicos/{s}/upload-foto`: o `{s}` passa a vir do registro criado pelo servidor. T-16/T-17: cada visita precisa de fotos e conserto; a reatribuição cria visita nova sem fotos. T-28/T-29: os negativos podem passar por falso positivo (422 por falta de equipamento) — assertar a mensagem, não só o código. T-02: o 400 de pausada vem da checagem de pausa — assertar a mensagem.

### 11.2 Testes de confidencialidade e integridade (v0.6)

**Resultado real em 08/11/2026 (SQLite):** 414 testes passando no backend (09/11/2026), dos quais 42 em `backend/tests/chamados/test_cifragem_integridade.py` (T-60 a T-99 abaixo; os IDs agrupam cenários, então não há correspondência 1:1 com as funções de teste). Os T-91 a T-93 usam um SQLite temporário "pós-0011" com dados em claro para exercitar o script de migração. **Não executados em PostgreSQL/Supabase**: unicidade do índice cego, tipos `text`/`jsonb`, `CHECK` de hash e comportamento real de `sslmode` precisam de teste equivalente à produção.

| ID | Cenário | Esperado |
|---|---|---|
| T-60 | Cifrar duas vezes o mesmo valor | Prefixo `enc1:`, valores diferentes (nonce novo), ambos decifram igual |
| T-61 | Bit alterado na tag; valor colado em outra coluna (contexto); valor sem prefixo | `ErroDecifragem` nos três |
| T-62 | Cifrar/decifrar bytes com contexto trocado | Falha de autenticação |
| T-63 | Índice cego: determinístico, depende do contexto e do valor, `None` → `None` | 64 hex; diferentes quando devem ser |
| T-64 | Criar técnico e ler o banco por SQL cru | CPF/CNPJ/telefone/banco/agência/conta/PIX com `enc1:`, nada em claro; `cnpj_idx` ≠ dígitos; API devolve em claro |
| T-65 | CNPJ duplicado sem máscara | 409 pelo índice cego |
| T-66 | Valor cifrado adulterado no banco | Leitura falha (`ErroDecifragem`) |
| T-67 | Texto puro em coluna cifrada | Erro com `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false`; lido com `true` |
| T-68 | CPF do cliente após `finalizar-atendimento` | Cifrado no banco; decifrado pelo ORM |
| T-69 | Chaves ausentes / base64 inválido / tamanho ≠ 32 / repetidas | A aplicação não inicia (`ValueError`) |
| T-70 | Upload com `sha256` correto; hash errado; hash malformado | 200 com `sha256` gravado; 422 sem gravar arquivo nem registro; 422 |
| T-71 | Upload sem hash | O servidor calcula e grava o seu |
| T-72 | `SHA256_ORIGEM_OBRIGATORIO=true` sem hash | 422 `HASH_AUSENTE` |
| T-73 | `upload-deslocamento` com hash | `visita.arquivos_sha256` preenchido |
| T-74 | Assinatura com `assinatura_sha256` errado/correto | 422 / 200 e `assinatura_sha256` = hash dos bytes originais |
| T-75 | `/api/sync/arquivos`: hash errado, correto, reenvio igual, mesmo id com outro conteúdo | 422 (`codigo`), 200, `duplicado`, 409 |
| T-76 | Finalizar atendimento | `selo_integridade` (64 hex) e `selo_versao = 1`; verificação `integro`; ação `INTEGRIDADE_VERIFICADA` auditada |
| T-77 | Verificação por técnico, outro técnico e sem token | 403, 403, 401 |
| T-78 | `UPDATE` direto no nome do cliente | `adulterado` com `selo_divergente` |
| T-79 | `UPDATE` direto em `km_fim_ida` | `adulterado` |
| T-80 | Trocar o arquivo de uma foto em disco; depois apagá-lo | `arquivo_divergente:*`; `arquivo_ausente:*` |
| T-81 | Alterar um byte do `.enc` da assinatura | `arquivo_adulterado:assinatura` |
| T-82 | Selo anulado no banco (a visita consta como selada no `log_acao`) | `adulterado` com `selo_removido` (não `sem_selo`) |
| T-82b | Visita legada: sem selo na visita **e** sem selo no `log_acao` | `sem_selo` (não é adulteração) |
| T-83 | Visita em atendimento (não finalizada) | `nao_finalizada` |
| T-84 | Admin corrige materiais após a OS Finalizada | Selo muda, verificação continua `integro`, `SELO_RESSELADO` com anterior e novo |
| T-85 | Resposta de erro de regra | Corpo com `codigo` estável |
| T-86 | Assinatura em disco | Arquivo `.enc` ilegível como imagem; `/static/assinaturas/<arquivo>` → 404 |
| T-87 | `GET .../assinatura` | Técnico atribuído e admin: 200, bytes idênticos ao original, `no-store`; outro técnico 403; sem token 401 |
| T-88 | Assinatura antiga em claro | Ainda servida até a conversão |
| T-89 | `ler_arquivo_por_url` com `../` e `None` | `None` (sem path traversal) |
| T-90 | HSTS | Ausente fora de produção; presente em toda resposta (inclusive 404) com `ENV=production` |
| T-90b | `_connect_args`: SQLite → `{}`; PostgreSQL → `sslmode=require`; `verify-full` + raiz; `disable` recusado em produção e aceito (com aviso) fora dela; valor desconhecido → erro | Conforme descrito |
| T-91 | Script de migração: cifra, preenche `cnpj_idx`, é idempotente | Segunda execução não altera nada |
| T-92 | Script: `--dry-run` não grava; `--decifrar` reverte | Verificado |
| T-93 | Script: converte assinatura, confere por SHA-256, preserva o original sem `--apagar-originais`, preenche hashes sem inventar os de arquivos ausentes | Verificado |

| T-94 | Selo trocado por outro valor | `selo_divergente` e `selo_diverge_da_auditoria` |
| T-95 | Finalizar atendimento | O selo e `selo_versao` constam no `payload` de `ATENDIMENTO_FINALIZADO` do `log_acao` |
| T-96 | **Regressão do item 1 da revisão.** Depois de finalizar o atendimento e antes da volta: upload de comprovante de pedágio, `PATCH` de `valor_pedagio`/`valor_frete_devolucao`, reenvio da foto da ida | Verificação continua `integro`; o arquivo do comprovante adulterado é acusado (`arquivo_divergente:comprovante_pedagio`) — fora do selo, mas com hash conferido. O teste **falha** se o pedágio voltar ao selo (verificado por mutação) |
| T-97 | Fluxo completo até a OS `Finalizado` (volta, custo congelado) | `integro` |
| T-98 | Desativar o técnico entre o atendimento e a volta (OS vai a `Pendente`, sem técnico) | `integro` |
| T-99 | `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT`: padrão `false`; `true` recusado com `ENV=production`; `DB_SSLMODE=require` em produção registra aviso de certificado não validado | Conforme descrito |

**Testes a executar antes de qualquer SEG-22 a SEG-28 virar *verificado* (plano, não resultado):** repetir T-64/T-65/T-78 a T-84 contra PostgreSQL equivalente ao de produção; restaurar um backup em ambiente limpo; conectar com `verify-full` e certificado inválido (deve falhar); `curl` sem TLS contra o deploy e conferir HSTS; executar o app Android em aparelho (captura → fila offline → envio → `HASH_DIVERGENTE` provocado) e o build de produção sem HTTP puro.

### 11.3 Testes do armazenamento privado (v0.6)

**Resultado real em 09/11/2026:** `test_storage_privado.py` (cliente do Storage com **transporte HTTP simulado**, rota de arquivos com bucket em memória, `/static`, configuração) e `test_migracao_storage.py` (script de migração com SQLite + bucket em memória) passam em SQLite. A conformidade com o servidor **real** foi verificada à parte, manualmente, por `scripts/testar_storage.py` (6/6) e pela migração (17/17 conferidos). O `conftest.py` impede que a suíte use o Storage real.

| ID | Cenário | Esperado |
|---|---|---|
| T-100 | Upload ao bucket | `POST /storage/v1/object/<bucket>/<area>/<nome>` com `x-upsert: false`, `Content-Type` e a chave de serviço |
| T-101 | Chave nova `sb_secret_...` vs chave antiga JWT | Nova: só `apikey`; antiga: `apikey` e `Authorization` |
| T-102 | Download | Endpoint `object/authenticated`; objeto inexistente (404, ou 400 com `not_found`) vira `None` |
| T-103 | Remoção de objeto inexistente | Sem erro (idempotente) |
| T-104 | Falha do Storage (500 ou rede) | 503 sem vazar a chave nem registrá-la no log |
| T-105 | Referência inválida (`../`, `/`, área desconhecida, vazio) | `ValueError`, nenhuma requisição é feita; nome com caracteres especiais vai codificado |
| T-106 | Configuração | `local`/`supabase`; produção sem Supabase, só uma das variáveis e URL `http://` são recusadas |
| T-107 | Com o bucket (em memória) | Foto e assinatura **não tocam o disco**; assinatura chega cifrada como `application/octet-stream` |
| T-108 | `GET .../arquivos/conteudo` | Admin e técnico da OS: 200 com os mesmos bytes e `Cache-Control: private`; outro técnico 403; sem token 401 |
| T-109 | Arquivo de outra OS, assinatura, referência inventada ou ausente do bucket | 404 (anti-IDOR) |
| T-110 | `/static/uploads/*` e `/static/assinaturas/*` | 404 mesmo com o arquivo no disco |
| T-111 | Verificação de integridade lendo do bucket; objeto trocado no bucket | `arquivo_divergente:*` |
| T-112 | Script de migração | Dry-run não grava; sobe e confere; não sobrescreve (`conflito`); hash do banco divergente não sobe; órfão só com `--incluir-orfaos`; assinatura em claro não sobe; `--apagar-locais` só apaga o confirmado; falha na conferência pós-upload interrompe sem apagar |

## 12. Plano de correção (backlog ordenado)

Ordem de execução. Cada item cita o ID do PRD.

> **Situação em 08/11/2026 (v0.5):** itens 24a, 25, 26 e 29 **implementados no backend** (testes em SQLite, 346 passando); item 24: migrações `0007` e `0009` **aplicadas no Supabase real em 08/11/2026 via MCP** (a OS existente, já Finalizada, não precisou de backfill); item 27: painel web (`web/`) **implementado** (`tsc` e `vite build` ok, **não executado** em navegador); item 28: app ajustado e com **outbox offline** (`tsc`/`lint` ok, **não executado** em aparelho); item 30: T-37 a T-59 e T-18/19/20/56 feitos para o backend (SQLite), sem execução em PostgreSQL; `scripts/smoke_api.py` e `ROTEIRO_TESTE_API.md` reescritos para a v0.5 (smoke validado só contra SQLite temporário).
>
>
> **Situação em 07/11/2026 (backend, testes só em SQLite):** implementados os itens 1 (PR-05), 2 (PR-10), 4 (PR-04), 9 (PR-06, endpoint `/auth/me`), 12 (PR-13), 16 (PR-18) e 19 (PR-21); item 17 (PR-19) parcial (trava de ambiente e `AUTO_CREATE_TABLES`; **Alembic pendente**); item 18 (PR-20) parcial (`log_acao` para ações de OS; **auditoria de login e de CRUD pendente**); item 10 (PR-03, Storage privado) **pendente**; item 20 (PR-17, cookie `HttpOnly`) **pendente**. Itens de painel e app (5, 6, 7, 8, 11, 13, 14) não foram reavaliados nesta revisão documental.

| Ordem | ID | Ação | Onde | Dependência |
|---:|---|---|---|---|
| 1 | PR-05 | Validar usuário ativo a cada requisição (`get_current_user` consulta o banco) | `core/security.py` | — |
| 2 | PR-10 | Persistir nome, CPF validado e assinatura nas colunas da visita; criar migration e testes de CPF/assinatura | `chamados.py`, `models/visita.py`, schemas | Decisão de negócio v0.2/v0.3; verificar implementação real |
| 3 | PR-11 | Tornar campos de horário opcionais no schema de resposta `Visita` e `km_total ≥ 0` | `schemas/visita.py` | — |
| 4 | PR-04 | Remover `POST /concluir` e impedir qualquer atualização direta de status para `Finalizado`; finalizar somente ao completar a volta sem pausa | `chamados.py`, serviços, painel | Decisão confirmada RF-14/TR-02 |
| 5 | PR-07 | Padronizar status no painel para os valores do enum do backend. Remover `CANCELADO`, `CONCLUIDO`, `EM_ATENDIMENTO`, `AGENDADO` | `chamadoService.ts`, `types.ts`, `StatusBadge.tsx` | — |
| 6 | PR-08 | Permitir pausa por admin com as mesmas regras de estado, registrar autor/papel e remover a ação de retomar | `DetalheChamadoView.tsx`, `chamados.py` | Decisão confirmada RN-30 |
| 7 | PR-01 | Remover `repairTecnicoProfile` e o botão associado | `AdminDashboardView.tsx`, `apiClient.ts` | — |
| 8 | PR-02 | Remover fallbacks com dados fictícios em `getTecnicos`, `getTecnico`, `getChamados` | `apiClient.ts`, `chamadoService.ts` | — |
| 9 | PR-06 | Criar `GET /api/auth/me` ou remover a chamada no app | `auth.py`, `tecnico.ts` | — |
| 10 | PR-03 | Migrar fotos, comprovantes e assinaturas do disco local para o bucket privado Supabase Storage. **v0.6: concluído em 09/11/2026 (17 arquivos migrados e conferidos). Pendentes: validar o painel em navegador e decidir `--apagar-locais`.** (O bucket já foi limpo dos objetos de teste, seção 9.) | `file_service.py`, `storage_service.py`, `chamados.py`, operação | Chave de serviço no `.env` (feito) |
| 11 | PR-09 | Criar fluxo/tela de reagendamento no painel, habilitado somente em `Aguardando Reagendamento` e `Agendado` antes da ida | `ModalDetalheOSAdmin.tsx` | Regras de reagendamento confirmadas na v0.3 |
| 12 | PR-13 | Implementar validador de transições (seção 5.3) e erro 409 | `chamado_service.py` | Itens 4 e 5 |
| 13 | PR-14 | Mover URL base do app para variável de ambiente `EXPO_PUBLIC_API_URL` | `frontend/src/api/api.ts` | — |
| 14 | PR-15 | Aplicar os cinco motivos oficiais de pausa e validação de `Outro` em app, painel e backend | três repositórios | Lista confirmada RN-29 |
| 15 | PR-12 | Corrigir chaves do cálculo de custos (`id_visita`, `id_os`) | `custo_service.py` | — |
| 16 | PR-18 | CORS por variável de ambiente | `main.py` | — |
| 17 | PR-19 | Adotar Alembic. Trava de ambiente em `resetar_banco.py`. Atualizar README (PostgreSQL) | backend | — |
| 18 | PR-20 | Auditoria: tabela `log_acao` (id, id_os, id_tecnico/admin, acao, criado_em, payload) e remover `print` | backend | — |
| 19 | PR-21 | Mensagem única de login | `auth.py` | — |
| 20 | PR-17 | Avaliar cookie `HttpOnly` no painel | painel, backend | Decisão de arquitetura |
| 21 | PR-16 | Definir e documentar um identificador de OS gerado/fornecido pela API se o código amigável for requisito do contrato; remover geração isolada no frontend | API, modelo OS, painel | Decisão técnica a detalhar entre PO e Backend; não é pendência de regra de negócio |
| 22 | PR-22 | Centralizar parâmetros globais de custo no backend; remover endpoints/tela por técnico e criar snapshot em `custo_os` | backend, DBA | Decisão v0.3; sem UI do técnico |
| 23 | PR-23, PR-24, PR-26 | Limpeza e higiene | vários | — |
| 24 | PR-37 | **(v0.5)** Inventário, backup e migração de dados legados de equipamento (4.9): tabelas, `is_legado`, backfill, relatório de exceções, RLS | `backend/migrations/0007_*` (próximo número livre), DBA | Decisões Q-EQ1 a Q-EQ5 já confirmadas (PRD 11.1.2); ensaio em dump (dev = produção) |
| 24a | RN-49 | **(v0.5)** Backend: correção administrativa de OS Finalizada (upload de foto e `DELETE .../fotos/{id_foto}` pelo admin, `PATCH` só de `materiais_utilizados`, trava da última foto, auditoria `FOTO_CORRIGIDA_ADMIN`/`MATERIAIS_CORRIGIDOS_ADMIN`) e tela no painel | `chamados.py`, `visita_service.py`, painel | Itens 25 e 26 |
| 25 | PR-38 | **(v0.5)** Backend: catálogo `/api/equipamentos`, vínculo `/api/chamados/{id}/equipamentos`, `equipamentos[]` em `ChamadoCreate`/`Chamado`, registro de serviço por equipamento criado pelo servidor, auditoria | `endpoints`, `services`, `models`, `schemas` | Item 24 |
| 26 | PR-39, PR-40, PR-42, PR-43 | **(v0.5)** Backend: `extra = "forbid"` na entrada de serviço, `POST .../servicos` 410, `salvar-conserto`, travas TR-12/TR-13 no `visita_service`, regras de fase do `upload-foto`, `EstadoVisita` ampliado | `visita_service.py`, `chamados.py`, schemas | Item 25 |
| 27 | PR-25, PR-38 | **(v0.5)** Painel: tela de modelos (CRUD com desativação lógica) e seção "Equipamentos" na criação/detalhe da OS (vários, modelo ativo + série, sem duplicata, somente leitura após o início); remover série gerada e defeito fixo | painel (Fast-IA-Studio) | Item 25 |
| 28 | PR-41 | **(v0.5)** App: equipamentos da OS somente leitura, foto de defeito antes de iniciar, "Salvar conserto", botões desabilitados com a pendência do servidor, remoção de "Adicionar equipamento" e dos campos de série/nome | `[id].tsx`, `registroEquipamento.tsx`, `RegistroFotoDefeito.tsx`, `utils/visita.ts`, `api/*.ts` | Itens 25 e 26 |
| 29 | PR-44 | **(v0.5)** Atualizar o contrato de sincronização (eventos, cache, códigos `FOTO_DEFEITO_AUSENTE`/`CONSERTO_INCOMPLETO`) quando `/api/sync` for implementado | backend, app | Sincronização offline (pendente) |
| 30 | — | **(v0.5)** Atualizar helpers e testes existentes e criar T-37 a T-59; executar em PostgreSQL equivalente ao de produção | `backend/tests/` | Itens 24 a 26 |
| 31 | SEG-22, SEG-23 | **(v0.6)** Cifragem AES-256-GCM dos campos sensíveis, índice cego do CNPJ, chaves validadas; migrações `0011`/`0012` e script de cifragem dos dados existentes. **Backend e dados implementados** (SQLite + Supabase conferido por consulta). Pendente: cofre de segredos e rotação | `core/crypto.py`, `models`, `migrations`, `scripts` | Backup |
| 32 | SEG-24 | **(v0.6)** Hash SHA-256 de todo arquivo (servidor sempre; origem obrigatória): backend, painel e app (fila com schema v2). **Implementado**; app/painel não executados | `file_service.py`, endpoints, `offline/*`, `apiClient.ts` | — |
| 33 | SEG-25 | **(v0.6)** Selo HMAC por visita, ressêlo na correção administrativa e `GET .../verificar-integridade`. **Implementado** (SQLite). Decidir (PO) se a volta/custo devem entrar no selo | `integridade_service.py`, `visita_service.py`, `servico_service.py` | Item 32 |
| 34 | SEG-26, SEG-09 | **(v0.6)** Assinatura cifrada + rota autenticada + painel com `blob:`; fotos, comprovantes e fotos de deslocamento em bucket privado (`storage_service`, `arquivos/conteudo`, `FotoSegura`, `/static` removido). **Implementado e migrado** (09/11/2026). Pendente: painel em navegador, remoção das cópias locais, cifragem das fotos pela aplicação (opcional) | `file_service.py`, `storage_service.py`, `chamados.py`, `FotoSegura.tsx` | Item 31 |
| 35 | SEG-27 | **(v0.6)** TLS: `sslmode`, HSTS, `usesCleartextTraffic=false`. **Implementado**; banco com `verify-full` e certificado raiz conferido no ambiente real (09–11/11/2026); HSTS conferido via túnel HTTPS (11/11/2026). Pendente: HTTPS no deploy definitivo e build Android de produção | `database.py`, `main.py`, `app.config.ts` | Infraestrutura |
| 36 | SEG-28 | **(v0.6)** Backup (`backup_banco.py`) implementado; pendente: restauração testada, `pg_dump`, cifragem do backup, retenção (`backend/migrations/` já versionada) | `scripts/`, operação | — |

## 13. Ordem de implementação recomendada (cronograma sugerido)

1. **Segurança e integridade (itens 1 a 4):** é o que pode causar dado errado ou acesso indevido. Antes de qualquer nova funcionalidade.
2. **Contrato entre painel e API (itens 5 a 9):** deixa o painel funcionando com o backend atual, sem remendos.
3. **Armazenamento (item 10):** necessário antes de qualquer uso em produção.
4. **Fluxos faltantes (itens 11 a 14):** reagendamento no painel, transições, configuração do app.
5. **Qualidade e operação (itens 15 a 23).**

Cada item deve ter teste da seção 11 antes de fechar.

## 14. Histórico de versões

| Versão | Data | Alterações |
|---|---|---|
| 0.2 | 29/10/2026 | Contrato inicial alinhado ao PRD v0.2. |
| 0.3 | 29/10/2026 | Estados Pendente/Aberto, reagendamento, custos globais, conflito offline, sessão 24 h sem refresh, upload 15 MB, Storage privado, desempenho e escopo sem ajudantes/notificações. |
| 0.6.1 | 11/11/2026 | Verificações no ambiente real (cabeçalho e seção 8): RLS conferido em todas as tabelas, sem políticas (SEG-12, SEG-20); TLS `verify-full` com certificado raiz, teste negativo e SSL obrigatório no servidor (SEG-27); HSTS conferido via HTTPS. Sem mudança de contrato. |
| 0.6 | 08/11/2026 | **Confidencialidade e Integridade.** Cifragem AES-256-GCM de campos sensíveis (`TextoCifrado`, `enc1:`) com índice cego do CNPJ (4.1, 4.4); SHA-256 de todo arquivo, calculado no aparelho/navegador e conferido pelo servidor (6.8, 6.12); selo HMAC-SHA256 por visita e `GET .../verificar-integridade` (4.4, 6.6, 8.1); assinatura cifrada em disco e `GET .../assinatura` autenticado, `/static/assinaturas` removido (6.6, 9); TLS (`DB_SSLMODE`, HSTS, Android sem HTTP puro); `ErroRegra` com `codigo`; variáveis `DATA_ENCRYPTION_KEY`, `INDEX_KEY`, `INTEGRITY_KEY`, `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT`, `SHA256_ORIGEM_OBRIGATORIO`, `DB_SSLMODE`, `DB_SSLROOTCERT` (2); decisões D1 a D6 (0.3); nova seção 8.1 (decisões criptográficas, chaves, matriz dos quatro pilares, riscos residuais); SEG-22 a SEG-28 e atualização do SEG-09; T-60 a T-93 (11.2); backlog 31 a 36. Migrações `0010` a `0012` e cifragem dos dados **aplicadas no Supabase real**; backup e script de migração. **Revisão de 08/11/2026:** selo sem os dados que mudam até o fim da volta e com cópia no `log_acao` (detecta selo removido); `ENCRYPTION_ALLOW_LEGACY_PLAINTEXT` desligado por padrão e recusado em produção; aviso de `sslmode=require`; riscos residuais explícitos (AAD por coluna, hash e arquivo na mesma área do app, fotos públicas); uploads diretos do app passam a enviar o hash. **Armazenamento privado (08/11/2026):** buckets `fast-ariam-privado` e `-dev` criados no Supabase (`0013`), `storage_service`, rota `arquivos/conteudo`, `/static` removido, painel com `FotoSegura`, scripts `migrar_arquivos_para_storage.py` e `testar_storage.py`; **executado em 09/11/2026:** `testar_storage.py` 6/6 no Supabase real; 17 arquivos migrados e conferidos; 5 órfãos excluídos do disco. Incidente: a suíte de testes chegou a gravar ~503 objetos de teste no bucket real antes de o `conftest.py` ser blindado (registro na seção 9); bucket limpo em seguida, com autorização do responsável (503 objetos removidos; restam os 17 legítimos). **Nenhum controle verificado em PostgreSQL; não há não repúdio criptográfico.** |
| 0.5 | 08/11/2026 | Regra de equipamento da OS (backend e testes SQLite implementados em 08/11/2026; migrações aplicadas no Supabase real; painel e app implementados mas não executados): catálogo `equipamento_modelo`, vínculo `os_equipamento` (modelo + série único por OS), `servico_equipamento` com `id_os_equipamento`, `conserto_salvo_em` e `is_legado` (4.5, 4.8); migração em fases com `is_legado` (4.9); registro de serviço por equipamento criado pelo servidor (6.5.3), `POST .../servicos` 410, `salvar-conserto` e regras de fase do upload (6.7); travas TR-12/TR-13/TR-14 em iniciar e finalizar atendimento com 409 (5, 6.6); `EstadoVisita` com `equipamentos[]` e bloqueios (6.6.3); novo capítulo 6.13 (catálogo, vínculo, auditoria, concorrência); sincronização com `FOTO_DEFEITO_AUSENTE`/`CONSERTO_INCOMPLETO` e SY-08/SY-09 (6.12); validações e erros (7, 10); SEG-20/SEG-21 (8); T-37 a T-59 e regressões esperadas (11.1); backlog 24 a 30 (12). **Confirmações do responsável (08/11/2026) incorporadas:** exigência por equipamento da OS; OS sempre com ≥ 1 equipamento (TR-15); edição do admin só até o início do atendimento e de volta apenas com a OS Finalizada, para corrigir fotos comprobatórias e materiais (RN-49, 6.13: rotas de correção, trava da última foto, auditoria, custo congelado não recalculado); renomear modelo reescreve o histórico; T-58 e T-59. Em aberto: Q-EQ6 e Q-EQ7. |
| 0.4 | 07/11/2026 | Decisões do PO: RN-08a resolvida (desatribuição automática na desativação do técnico), visita automática ao entrar em Agendado, máscara canônica de CPF/CNPJ do técnico (CPF do cliente só dígitos), administrador não recebe OS, tempo de serviço de visita pausada vale zero no custo, foto de conserto 960 × 1280 em qualquer orientação, ambiente dev/produção compartilhado como risco aceito. Contratos implementados incorporados: `ocorrido_em`, `Visita` ampliada, `finalizar-dados` 410, remoção de `/concluir` e `DELETE /chamados`, `PATCH` da OS restrito, reagendamento com validações, uploads (409/413/422), `GET /custos` com snapshot, `/auth/me`, `CORS_ORIGINS`/`ENV`/`AUTO_CREATE_TABLES`/`SECRET_KEY`. Seção 8 com status honesto; novas pendências SEG-16 a SEG-19; T-08 e T-17 reescritos; T-28 a T-36 adicionados. |

## 15. Glossário

| Termo | Definição |
|---|---|
| OS / Chamado | Ordem de serviço. No código aparece como `chamado` e `ordem_servico` |
| Visita | Uma ida do técnico ao cliente. Uma OS pode ter várias visitas (reagendamentos) |
| Pausa | Interrupção do atendimento com motivo, enquanto a OS aguarda nova data |
| Deslocamento ida / volta | Trajeto até e a partir do cliente, com km e odômetro |
| Estado da visita | Resposta de `GET .../estado`, que diz quais botões o app deve exibir |
| Pendente | OS não finalizada e sem técnico atribuído (criação sem técnico, conflito offline ou desativação do técnico); não representa pendência técnica do serviço |
| Visita aberta | Visita ainda não finalizada de uma OS; criada automaticamente quando a OS entra em `Agendado` (RN-11a) |
| Máscara canônica | Forma única de armazenar CPF (`000.000.000-00`) e CNPJ (`00.000.000/0000-00`) do técnico, para garantir unicidade e consistência |
| Desativação lógica | `is_active = false` ou `is_cancelled = true`, sem apagar o registro |
| Evento de sincronização | Ação registrada no aparelho (por exemplo, "deslocamento de ida iniciado"), com id próprio e horário real, enviada ao servidor quando há conexão |
| Outbox | Fila local do app com os eventos e arquivos ainda não confirmados pelo servidor |
| Idempotência | Propriedade de repetir o envio do mesmo evento sem gerar efeito duplicado |
| Modelo de equipamento | Item do catálogo mantido pelo admin; só o nome (ex.: "Freezer vertical modelo X"). Desativado, nunca excluído |
| Equipamento da OS (`os_equipamento`) | Vínculo de um modelo com um número de série em uma OS, feito pelo admin; pertence à OS e é compartilhado entre as visitas. O técnico só o lê |
| Conserto salvo | Marca (`conserto_salvo_em`) gravada quando o técnico aciona "Salvar conserto" no equipamento, com ao menos um defeito principal; pré-condição para finalizar o atendimento |
| Pendência de equipamento | Equipamento da OS sem foto de defeito (bloqueia iniciar) ou sem conserto salvo / foto de conserto (bloqueia finalizar), listada no 409 e em `GET .../estado` |
| Congelamento de custo | Gravar o cálculo no momento da finalização da OS, para que mudanças posteriores nos valores de referência não alterem o histórico |
