# Fast Ariam — Skills de agentes de software (PRD v0.5 / SDD v0.7)

Pacote com seis skills especializadas alinhadas ao PRD v0.5 e à SDD v0.7:

- **PO:** requisitos, regras de negócio, escopo, backlog e critérios de aceite.
- **QA:** estratégia de testes, regressão, contrato, migrações, offline e evidências.
- **DBA:** PostgreSQL, modelagem, constraints, Alembic, integridade, backup e Storage.
- **Backend:** API FastAPI, RBAC, transições, sincronização, uploads e cálculo global de custos.
- **Frontend:** painel React e app Android Expo/React Native; referência visual obrigatória no aplicativo do técnico.
- **Security:** AppSec, modelagem de ameaças, confidencialidade, autenticação assimétrica, integridade, assinatura digital, não repúdio e gestão de chaves.

## Estrutura

```text
fast-ariam-agent-skills/
├── README.md
├── AGENT_ROUTING.md
├── PROJECT_CONTEXT.md
├── references/
│   ├── PRD-Fast-Ariam.md
│   └── SDD-Fast-Ariam.md
├── fast-ariam-po/SKILL.md
├── fast-ariam-qa/SKILL.md
├── fast-ariam-dba/SKILL.md
├── fast-ariam-backend/SKILL.md
├── fast-ariam-frontend/SKILL.md
└── fast-ariam-security/SKILL.md
```

## Uso

1. Disponibilize o diretório da skill no local reconhecido pelo orquestrador de agentes.
2. Mantenha `PROJECT_CONTEXT.md`, `AGENT_ROUTING.md` e `references/` no contexto compartilhado do projeto.
3. Use PO para refinar demandas; convide DBA/Backend/Frontend conforme a camada afetada e QA para validar.
4. Acione Security para modelagem de ameaças, criptografia, gestão de chaves, autenticação, integridade, assinatura, auditoria e incidentes.
5. Não invoque todos os agentes em tarefas simples. Siga o fluxo de handoff do `AGENT_ROUTING.md`.

## Decisões centrais do produto — PRD v0.3 a v0.5 e SDD v0.3 a v0.7

- `Pendente` = OS não finalizada sem técnico; `Aberto` é legado.
- Reagendamento em `Pausado` é proibido até finalizar deslocamento de volta.
- Custos são globais e congelados na finalização; técnico não altera valores.
- Conflito offline incompatível leva a OS não finalizada para `Pendente`, sem técnico, com auditoria.
- Offline por até 24 h, sem refresh token, preservando outbox.
- Imagens JPEG/PNG até 15 MB; Supabase Storage privado.
- Ajudantes e notificações fora do escopo.
- Desativação de técnico desatribui automaticamente todas as OS não finalizadas e não canceladas (RN-08a, resolvida em 07/11/2026).
- **Equipamento da OS (v0.5, 08/11/2026):** o técnico não cadastra equipamento; o admin mantém o catálogo de modelos e vincula modelo + série na OS (toda OS tem ao menos um equipamento). Atendimento só inicia com foto de defeito e só finaliza com conserto salvo + foto de conserto, por equipamento. Admin corrige fotos e materiais apenas com a OS Finalizada, e a correção de materiais recalcula o custo com os valores congelados (RN-49). Situação: backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 414 testes automatizados em SQLite (v0.6, 09/11/2026) e um smoke ponta a ponta da v0.5 (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), seguidas das migrações `0010` a `0013` da v0.6. Entre 09 e 11/11/2026 o backend foi executado contra esse PostgreSQL, o painel web foi aberto no navegador e o app do técnico foi usado contra o backend nas verificações manuais de segurança registradas na SDD v0.6.1 (RLS, TLS `verify-full`, storage privado, JWT adulterado, hash de upload, selo da visita e cifra adulterada); a suíte de regras de negócio ainda não foi repetida contra o PostgreSQL.
- **Confidencialidade e integridade (SDD v0.6 e v0.7, 08 e 12/11/2026):** AES-256-GCM na aplicação (`TextoCifrado`), SHA-256 dos arquivos e selo de integridade da visita; a v0.7 estendeu a cifragem ao contato principal do cliente, ao nome do signatário e ao nome/CPF do `sync_evento.payload`. Estado honesto da v0.7: Implementado (teste SQLite); aplicado no Supabase real em 12/11/2026 e conferido por consulta/script conforme declaração do responsável (evidências a anexar); sem backup pré-migração (desvio do runbook); não verificado pelo Security/QA (sem teste em PostgreSQL nem ensaio formal do DDL/rollback). Fila e cache do app, backups e histórico do provedor seguem com dado em claro.

O PRD v0.5 define o comportamento do produto; a SDD v0.7 define os contratos técnicos. A API é a única fonte de verdade. O painel e o app não acessam diretamente o Supabase.


## Segurança — quatro pilares

A skill Security orienta os controles de confidencialidade, autenticação, integridade e não repúdio. Ela não altera silenciosamente o contrato técnico: a SDD atual documenta JWT HS256 (segredo simétrico), enquanto autenticação assimétrica de tokens exige decisão arquitetural e plano de rotação de chaves. A assinatura manuscrita capturada como imagem também não deve ser descrita como assinatura digital criptográfica nem como prova automática de não repúdio.
