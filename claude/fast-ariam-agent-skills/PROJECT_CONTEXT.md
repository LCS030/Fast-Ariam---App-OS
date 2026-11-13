# Contexto compartilhado do projeto — Fast Ariam (PRD v0.5 / SDD v0.7)

Este arquivo é a referência compacta comum aos seis agentes. Para o contrato completo, consultar `references/PRD-Fast-Ariam.md` e `references/SDD-Fast-Ariam.md`. Em caso de divergência, a decisão de negócio do PRD v0.4 (07/11/2026) prevalece sobre texto legado da SDD v0.2/v0.3 ou sobre o código atual; a SDD (v0.4 a v0.7) traduz a decisão para o contrato técnico.

## 1. Produto e arquitetura

Fast Ariam (FAST Gôndolas & Check-outs) gerencia OS de manutenção de gôndolas e equipamentos de refrigeração. São três superfícies: painel administrativo web, aplicativo Android do técnico e API FastAPI. Painel e app comunicam exclusivamente com a API; nunca acessam PostgreSQL, Supabase SDK ou Storage diretamente.

Arquitetura: React web + Expo/React Native Android → HTTPS/API FastAPI → PostgreSQL gerenciado pelo Supabase. Fotos, comprovantes e assinaturas (estas cifradas com AES-256-GCM) ficam no bucket privado `fast-ariam-privado` do Supabase Storage desde 09/11/2026; `/static` não é mais servido.

## 2. Stack documentada

| Camada | Tecnologias |
|---|---|
| API | FastAPI 0.121.1, Pydantic 2.12.4, SQLAlchemy 2.0.44, psycopg2-binary 2.9.11, python-jose/JWT HS256, bcrypt, Pillow 12.1.1, Uvicorn 0.38.0 |
| Banco | PostgreSQL gerenciado pelo Supabase, `DATABASE_URL`, migrações Alembic a adotar |
| Painel | React 18.3, Vite 6, TypeScript 5.7, Tailwind 4, Recharts 3.10, lucide-react 0.475 |
| App técnico | Expo 54, React Native 0.81.5, React 19.1, expo-router 6, Axios 1.13, expo-image-picker 17; Android somente |

Verificar manifests reais antes de alterar dependências.

## 3. Papéis

- `admin`: equipe do escritório; administra clientes/técnicos/OS, atribui, pausa, reagenda e cancela. **Não recebe OS**: só o papel `tecnico` (ativo) é atribuível.
- `tecnico`: executa apenas OS atribuídas a ele no app Android; não administra clientes nem custos globais.
- `cliente`: empresa atendida, sem conta; fornece nome, CPF e assinatura na visita.

RBAC é aplicado no backend a cada requisição. Técnico inativo perde acesso mesmo com token previamente emitido.

## 4. Escopo

### Dentro

- Login por e-mail/senha, JWT, troca de senha.
- CRUD de clientes/técnicos, desativação lógica.
- Criação/atribuição/cancelamento/reagendamento de OS.
- Múltiplas visitas por OS; deslocamentos ida/volta; atendimento; defeitos, conserto, materiais e fotos sobre os equipamentos que já vêm na OS.
- **(v0.5)** Catálogo de modelos de equipamento (admin) e vínculo modelo + número de série na OS; correção administrativa de fotos e materiais em OS Finalizada (RN-49).
- Fotos, comprovantes de pedágio/frete, assinatura do cliente.
- Pausa por técnico e admin; reagendamento pelo admin.
- Cálculo de custo interno com parâmetros globais do sistema e snapshot na finalização.
- App offline por até 24 horas desde última autenticação online, com fila persistente e sincronização idempotente.
- Painel online com indicadores, OS, visitas, custos e histórico.

### Fora

Faturamento, NF, pagamentos, cobrança do cliente, notificações, relatório individual de OS, iOS, painel administrativo offline, multiempresa, estoque de peças e qualquer gestão de ajudantes. Não adicionar features fora do escopo sem decisão do PO/responsável.

## 5. Status oficiais da OS

| Status | Semântica | Observação |
|---|---|---|
| `Pendente` | OS criada, não finalizada, sem técnico atribuído | Status de abertura/triagem e de conflito offline. |
| `Agendado` | Técnico ativo atribuído e data prevista | Pode alterar data da visita somente antes do início da ida. |
| `Em Atendimento` | Técnico iniciou atendimento após finalizar ida | Admin ou técnico pode pausar. |
| `Pausado` | Visita em atendimento interrompida | Não pode reagendar até finalizar deslocamento de volta. |
| `Aguardando Reagendamento` | Volta concluída após pausa; aguarda nova data | Admin pode criar a próxima visita. |
| `Finalizado` | Volta concluída sem pausa ativa | Conclusão automática; custo congelado. |

`Cancelado` não é enum; é `is_cancelled` + motivo/data/autor. OS finalizada ou já cancelada não pode ser cancelada novamente. `Aberto` é legado e deve ser migrado para `Pendente` quando não houver técnico. Registros antigos `Pendente` com técnico atribuído precisam ser inventariados antes da migração. `Pendente` sempre implica `id_tecnico_atribuido IS NULL`.

## 6. Fluxos de negócio

### Criação e atribuição

- Criar OS sem técnico → `Pendente`.
- Criar OS com técnico ativo → `Agendado`.
- Atribuir técnico a OS `Pendente` → `Agendado`.
- **RN-08a (resolvida em 07/11/2026):** ao desativar um técnico, todas as OS dele não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) voltam a `Pendente`, sem técnico, na mesma transação; visitas, fotos, serviços e pausas ficam como histórico; Finalizadas/canceladas não mudam; ação auditada em `log_acao`. Ao reatribuir depois, visita iniciada pelo técnico anterior fica como histórico e é criada visita nova.
- **Visita automática:** toda OS que entra em `Agendado` ganha uma visita aberta na mesma transação; `data_visita` = `data_agendamento` ou, se vazia, hoje em America/Sao_Paulo. `POST /chamados/{id}/visitas` devolve 409 se já existe visita não finalizada.

### Equipamentos da OS (v0.5, confirmado pelo responsável em 08/11/2026)

**Situação (08/11/2026):** Backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 414 testes automatizados em SQLite (v0.6, 09/11/2026) e um smoke ponta a ponta da v0.5 (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), seguidas das migrações `0010` a `0013` da v0.6. Entre 09 e 11/11/2026 o backend foi executado contra esse PostgreSQL, o painel web foi aberto no navegador e o app do técnico foi usado contra o backend nas verificações manuais de segurança registradas na SDD v0.6.1 (RLS, TLS `verify-full`, storage privado, JWT adulterado, hash de upload, selo da visita e cifra adulterada); a suíte de regras de negócio ainda não foi repetida contra o PostgreSQL.

- O técnico **não** cadastra nem edita equipamento, modelo ou número de série. O admin mantém o catálogo de modelos (`equipamento_modelo`, só o nome; desativação lógica, nome único sem diferenciar maiúsculas) e vincula modelo + série na OS (`os_equipamento`; série única por OS), um ou mais por OS.
- **Toda OS tem ao menos um equipamento; OS sem equipamento não é criada** (422). OS legada sem equipamento não pode ser atribuída, reagendada nem iniciada até o vínculo.
- O servidor cria um `servico_equipamento` por equipamento da OS em cada visita; `POST .../servicos` responde 410.
- Atendimento só inicia com **foto de defeito de cada equipamento** (409 com pendências); só finaliza com **conserto salvo** (marca `conserto_salvo_em`, ≥ 1 defeito principal) e **foto de conserto** de cada equipamento (409). Vale por equipamento, a cada visita. Pausa dispensa essas exigências.
- Admin edita equipamento só até o início do atendimento; do início à finalização não edita; com a OS **Finalizada** pode corrigir apenas fotos comprobatórias e materiais (auditado; não remove a última foto do tipo; o custo é recalculado com os valores congelados). Só fotos e materiais são editáveis após a finalização; modelo/série ficam travados. Renomear modelo reescreve o histórico exibido.
- Sem pontos em aberto na regra de equipamento (Q-EQ6 e Q-EQ7 respondidos em 08/11/2026).

### Visita normal

1. Iniciar ida (km + foto do odômetro).
2. Finalizar ida (km + foto).
3. Registrar a foto do defeito de cada equipamento da OS (somente leitura).
4. Iniciar atendimento (exige o passo 3).
5. Registrar defeitos e materiais, salvar o conserto e tirar a foto do conserto de cada equipamento.
6. Finalizar atendimento com nome, CPF válido e assinatura na visita (exige o passo 5).
7. Iniciar e finalizar volta (km + fotos).
8. Finalizar volta sem pausa → OS `Finalizado` automaticamente e custo congelado.

### Pausa e reagendamento

- Só é possível pausar visita em atendimento e ainda não finalizada.
- Técnico e admin podem pausar. Registrar autor e papel.
- Motivos: `Peça pendente`, `Cliente ausente`, `Condições inseguras`, `Aguardando aprovação`, `Outro`; `Outro` exige descrição.
- Durante pausa não se finaliza atendimento; técnico finaliza deslocamento de volta → OS `Aguardando Reagendamento`.
- **Não** reagendar enquanto status `Pausado`. Somente depois da volta, em `Aguardando Reagendamento`, admin cria nova visita e encerra pausa.
- Em `Agendado` sem ida iniciada, admin altera a data da visita existente, sem criar uma nova visita.
- Não existe retomar pausa nem concluir OS manualmente.

## 7. Dados, imagens e custos

- Cliente: `codigo` obrigatório, inteiro e único.
- Assinatura pertence à visita; nome, CPF validado e assinatura são obrigatórios para finalizar atendimento.
- Foto de conserto: mínimo equivalente a 960 × 1280 px em qualquer orientação (menor lado ≥ 960 e maior lado ≥ 1280). Foto de defeito, odômetro e deslocamento não têm mínimo de resolução.
- CPF e CNPJ do **técnico** são armazenados com máscara canônica (CPF 14, CNPJ 18 caracteres); o CPF do **cliente** na visita fica só com dígitos (11).
- Todas as imagens: JPEG/PNG e até 15 MB por arquivo; validar no app, API e bucket.
- Ajudantes fora do escopo; não criar campos novos, tela ou cálculo. Campos antigos só podem permanecer por compatibilidade de histórico.
- Custo: interno, não cobrado do cliente. Parâmetros globais da configuração do sistema, não por técnico; técnico não altera. Congelar valores e cálculo em `custo_os` ao finalizar. O tempo de serviço de visita pausada conta zero no custo.

## 8. Offline e sessão

- Login inicial exige internet. App pode operar offline por até 24 horas após último login online bem-sucedido.
- Não implementar refresh token. JWT expira conforme configuração (30 min por padrão); se expirado, novo login online é exigido antes de sincronizar.
- Após 24h offline bloquear novas operações autenticadas até reconectar/login. Nunca apagar eventos/arquivos da outbox.
- Eventos usam `client_event_id`, `ocorrido_em` do aparelho e `recebido_em` do servidor. Reenvio é idempotente.
- Conflito administrativo incompatível na sincronização: rejeitar eventos conflitantes, colocar OS não finalizada em `Pendente` sem técnico e auditar `CONFLITO_ADMINISTRATIVO`; preservar eventos e arquivos sem descarte silencioso. Cancelamento/finalização já efetivados não são revertidos.

## 9. Storage e operação

- Bucket privado `fast-ariam-privado` no Supabase Storage (implementado na v0.6). A API valida a permissão sobre a OS e entrega o arquivo pelas rotas autenticadas `.../arquivos/conteudo` e `.../assinatura`; não emite URLs assinadas.
- Plano Free atualmente inclui 1 GB de storage e 5 GB de egress; bucket privado é suportado. Projeto Free pode pausar após uma semana de inatividade. Monitorar cotas e avaliar Pro para continuidade/volume de produção.
- Service key apenas no backend. Nenhum front acessa Storage diretamente.
- Sem rotina de exclusão automática nesta versão; aplicar acesso mínimo e backup.

## 10. Metas do produto e qualidade

| Objetivo | Meta inicial |
|---|---|
| Visitas com km/horários completos | 100% |
| OS finalizadas com assinatura/dados válidos | 100%; evidências fotográficas aplicáveis ≥ 95% |
| OS finalizadas com custo congelado | 100% |
| OS em Aguardando Reagendamento agendadas em até 2 dias úteis | ≥ 90% |
| Eventos/arquivos offline contabilizados sem perda silenciosa/duplicidade | 100%; 0 duplicidades |
| Divergências críticas/altas de contrato na release | 0 |
| API listagens/detalhes | p95 ≤ 2 s em 20 usuários simultâneos/1.000 OS de teste |
| Upload de imagem de 15 MB | ≤ 30 s em upload estável de 10 Mbps |

## 11. Pendências que permanecem

Não há decisão de negócio bloqueante em aberto (RN-08a foi resolvida em 07/11/2026). Já implementados: regra de equipamento da OS da v0.5, `/api/sync` com outbox e sessão offline de 24 h, Storage privado (SEG-09) e a camada de confidencialidade e integridade da v0.6. Pendências técnicas registradas, ainda **não implementadas**: Alembic; cookie `HttpOnly` no painel; rate limit de login; auditoria de login e de CRUD; CPF mascarado no painel é só visual (M3); vulnerabilidades transitivas das dependências do Expo.

**Risco aceito pelo PO (07/11/2026):** dev e produção compartilham o mesmo projeto Supabase nesta fase; Security mantém a ressalva (SEG-05, SEG-12, SEG-19).

**Status honesto dos controles:** os SEG-xx marcados como implementados na SDD têm apenas testes automatizados em SQLite (exceto os itens que a SDD v0.6.1 registra como conferidos no Supabase real); não os trate como verificados até haver teste em PostgreSQL/Supabase e parecer de QA/Security.

**v0.7 (12/11/2026, cifragem dos dados pessoais restantes, SEG-22 ampliado):** implementado e coberto por testes em SQLite (suíte 526 passando e 2 `xfail`, eram 414): `cliente.contato_principal_nome/telefone`, `visita.nome_cliente_assinatura` e as chaves `documento_cliente`/`nome_cliente` de `sync_evento.payload` cifrados. **Aplicação (12/11/2026, pelo responsável humano):** a migração `0014` e `scripts/cifrar_dados_existentes.py --campos --payload-sync` foram executados no Supabase real; o responsável declarou que as conferências passaram (`--verificar` código 0; B1 a B3 = 0; 3 colunas `text`; tela de clientes ok; `verificar-integridade` da OS 3 íntegro), mas **os prints ainda não foram anexados**. **Desvio do runbook: sem backup pré-migração** (os únicos backups são os de 08/11/2026, com dado em claro); o rollback (`--decifrar` → `0014_rollback.sql` → código anterior) não depende de backup. H3 (ajudante) não incluído, decisão pendente. **Estado: Implementado (teste SQLite); aplicado no Supabase real e conferido conforme declaração; não verificado pelo Security/QA** (sem teste em PostgreSQL nem ensaio formal do DDL/rollback). Em claro por decisão: `cliente.telefone` (comercial), dados cadastrais e textos livres; fila e cache do app (SEG-13) e backups também. Defeitos/riscos abertos: D-V07-2, D-V07-3, R-1 (SDD 8.1).

## 12. Precedência documental

1. Decisões confirmadas no PRD v0.5.
2. Contratos técnicos na SDD v0.7.
3. Código atual como evidência a ser comparada, não como definição de negócio.
4. Documentos legados v0.2 a v0.4, apenas para histórico; nunca prevalecem sobre v0.5.

## 13. Segurança e criptografia — contexto do agente Security

O agente Security deve avaliar o produto pelos quatro pilares definidos para o projeto:

- **Confidencialidade:** TLS/HTTPS em trânsito; bucket Supabase privado e autorização por OS; entrega de arquivos só pelas rotas autenticadas da API; proteção dos dados offline; criptografia de aplicação AES-256-GCM implementada (v0.6), com chaves simétricas distintas por finalidade, validadas na inicialização e mantidas fora do repositório. Nunca embutir segredo compartilhado em painel ou app.
- **Autenticação:** validar certificado TLS do servidor e, quando necessário, projetar autenticação assimétrica por pares de chaves. A SDD v0.4 documenta JWT HS256, que usa segredo compartilhado; não afirmar que esse mecanismo é assimétrico. Qualquer migração para RS256/EdDSA, mTLS ou chave por dispositivo precisa de análise de impacto, plano de ciclo de vida das chaves e aprovação antes de alterar contrato.
- **Integridade:** hashes criptográficos como SHA-256/384 para verificar arquivos/payloads; HMAC para integridade/autenticidade com segredo compartilhado; assinatura digital para conteúdo cuja autoria precise ser verificada. `client_event_id` e idempotência não são, por si, proteção criptográfica contra adulteração.
- **Não repúdio:** assinatura digital assimétrica verificável, vínculo da chave pública com identidade, política de rotação/revogação, evidência temporal e auditoria protegida. A imagem manuscrita recolhida atualmente na visita não é, sozinha, uma assinatura digital criptográfica nem prova suficiente de não repúdio. Necessidade jurídica/ICP-Brasil deve ser validada com PO e assessoria jurídica.

Não implementar algoritmo próprio. Preferir bibliotecas mantidas, cifras autenticadas (AEAD), gestão de chaves com KMS/secret manager quando disponível e separação de chaves por finalidade. Senhas continuam sendo armazenadas como hash adaptativo (bcrypt na SDD), nunca por criptografia reversível. O agente Security produz threat model, matriz `SEG → ameaça → controle → componente → teste → evidência`, riscos residuais e handoffs para Backend, DBA, Frontend e QA.

Os requisitos SEG-01 a SEG-19 da SDD devem ser acompanhados como controles com status verificável; sua presença no documento não significa que estejam implementados nem verificados (ver legenda da SDD seção 8).
