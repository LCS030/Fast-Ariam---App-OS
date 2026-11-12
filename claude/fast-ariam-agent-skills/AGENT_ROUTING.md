# Coordenação e roteamento dos agentes — Fast Ariam

## 1. Objetivo

Coordenar PO, QA, DBA, Backend, Frontend e Security sem duplicar responsabilidades nem permitir que cada agente mantenha sua própria interpretação do produto. Todos devem ler `PROJECT_CONTEXT.md` e consultar o PRD/SDD originais.

## 2. Qual agente chamar

| Tipo de tarefa | Agente primário | Agentes de apoio |
|---|---|---|
| Modelagem de ameaças, criptografia, gestão de chaves, confidencialidade, autenticação assimétrica, integridade, assinatura digital, não repúdio, revisão AppSec ou incidente | Security | Backend; DBA; QA; PO; Frontend conforme superfície |
| Nova funcionalidade, mudança de regra, priorização, escopo ou requisito ambíguo | PO | QA; Backend/Frontend/DBA conforme impacto |
| Testes, regressão, validação de aceite, reprodução de bug, análise de risco | QA | Agente técnico da camada afetada; PO para regra ambígua |
| Tabelas, colunas, constraints, índices, consultas, migrações, integridade, backup | DBA | Backend; QA |
| Rotas, autenticação, autorização, serviços, regras de negócio, sincronização, uploads, custos | Backend | DBA; QA; PO |
| Telas, navegação, componentes, formulários, estado visual, consumo da API, UX e acessibilidade | Frontend | Backend; QA; PO |

### Revisão ou implementação de segurança

1. Security identifica ativos, fronteiras de confiança, ameaças e controles atuais; diferencia evidência de proposta.
2. PO aprova qualquer alteração de escopo, fluxo de autenticação, assinatura, política de dados ou nível de garantia.
3. Backend/DBA/Frontend implementam os controles nas respectivas camadas; Security revisa o desenho e o resultado.
4. QA executa testes negativos e positivos para confidencialidade, autenticação, integridade e não repúdio, incluindo abuso de permissões, replay e adulteração.
5. A SDD recebe os novos requisitos `SEG`, contratos, decisões de chaves e evidências. Não declarar controle verificado sem testes reproduzíveis.

## 3. Sequência recomendada

### Feature sem alteração de banco

1. PO esclarece objetivo, usuário, escopo e critérios de aceite (ou valida que a demanda já está especificada).
2. Backend define/implementa o contrato quando houver mudança de API; Frontend consome o contrato existente ou atualizado.
3. QA cria/atualiza casos de teste e valida regressões.
4. PO verifica se a entrega corresponde ao resultado esperado.

### Feature com alteração de banco

1. PO define o resultado de negócio e aceite.
2. DBA propõe o modelo, constraints, migração, compatibilidade e rollback.
3. Backend valida o modelo de persistência e implementa serviços/endpoints sobre o novo contrato.
4. Frontend integra a API sem acessar o banco.
5. QA valida migração, integridade, API, UI e regressão ponta a ponta.
6. PO aceita ou devolve a entrega com pendências objetivas.

### Bug

1. QA ou agente técnico reproduz o bug com ambiente, passos, resultado atual e esperado.
2. PO entra quando a regra esperada não estiver definida ou quando houver impacto de escopo.
3. Agente responsável corrige a camada de origem. Não criar remendo de UI para ocultar violação de regra do backend.
4. QA adiciona teste de regressão e confirma o resultado.

## 4. Contrato de handoff entre agentes

Toda passagem de trabalho deve conter:

```text
ID / título:
Objetivo de negócio:
Requisitos e regras relacionados: RF / RN / RNF / CA / PR / TR / SEG / SY / T
Escopo incluído:
Fora do escopo:
Camadas afetadas: banco / API / painel / app / testes
Contrato ou decisão que muda:
Dependências:
Riscos e casos-limite:
Critérios de aceite:
Testes exigidos:
Dúvidas e propostas ainda não aprovadas:
Arquivos alterados:
Status: pronto / bloqueado / parcial
```

O agente que recebe o handoff deve confirmar os contratos relevantes e apontar inconsistências antes de codificar.

## 5. Regras para evitar conflitos

- PRD v0.5 governa o comportamento de negócio; SDD v0.5 governa o contrato técnico. Código atual é evidência de implementação, não a regra final.
- Nenhum agente pode alterar silenciosamente o significado de status, fluxo de visita, permissões, custo, CPF, fotos, pausa, cancelamento ou sincronização.
- Se uma proposta ou dúvida afeta comportamento, segurança, dados persistidos ou compatibilidade, abrir questão para PO/responsável antes de assumir.
- Mudança de API exige atualização da SDD/contrato, schemas, consumidores e testes relacionados.
- Mudança de banco exige migração versionada, estratégia de dados legados, rollback e verificação em ambiente não produtivo.
- Frontend não acessa Supabase diretamente e não implementa regra de negócio como autoridade.
- Backend não delega validação de segurança/estado para o frontend.
- QA não deve alterar o código de produção para fazer testes passarem; deve reportar falhas com evidência.
- Nenhum front pode exibir registros fictícios como fallback de erro.
- Não adicionar funcionalidades fora do escopo da versão sem aprovação do PO.

## 6. Portões mínimos de qualidade

Uma entrega não está pronta quando apenas compila. Verificar:

1. Requisito e IDs rastreáveis.
2. Contrato API/banco coerente entre app, painel, API e banco.
3. Permissões e validações executadas no servidor.
4. Fluxo de status e multi-visita preservados.
5. Migração segura e reversível quando houver alteração de schema.
6. Tratamento de loading, vazio, sucesso, falha e dados rejeitados nos fronts.
7. Nenhum dado fictício, segredo ou credencial exposta.
8. Operação offline idempotente e persistente quando aplicável.
9. Testes automatizados e regressões executados, com resultado informado.
10. UI do frontend coerente com as referências visuais do app do técnico.
11. Documentação atualizada e limitações explicitadas.
12. Status `Pendente` sempre sem técnico; `Aberto` não é persistido em novas operações.
13. Custos globais e congelados na finalização; sem configuração por técnico.
14. Sessão offline até 24 h sem refresh token; outbox preservada.
15. Imagens JPEG/PNG até 15 MB em bucket privado; leitura somente pelas rotas autenticadas da API, com autorização por OS (implementado na v0.6; URLs assinadas não são emitidas).
16. TLS/certificados válidos em trânsito; nenhuma chave/credencial privilegiada em front, bundle, log ou repositório.
17. Controles de autenticação, autorização, rotação/revogação de chaves e gestão de segredos revisados pelo Security.
18. Integridade de arquivos/eventos e auditoria verificadas; não declarar não repúdio criptográfico com base apenas na imagem de assinatura.

## 7. Definição de pronto por tipo

- **PO:** história refinada, prioridade definida, critérios verificáveis, dependências e dúvidas registradas.
- **DBA:** migração versionada, constraints e FKs validadas, dados preservados, plano de rollback, backup e teste de upgrade/downgrade quando aplicável.
- **Backend:** contrato documentado, validações server-side, RBAC, transações/erros apropriados, logs úteis e testes.
- **Frontend:** consumo fiel da API, estados completos, responsividade/usabilidade, aderência visual, permissões na interface e offline no app quando aplicável.
- **QA:** matriz requisito × teste, cenários positivos/negativos, regressão, evidências, severidade e parecer de release.
- **Security:** threat model, matriz de riscos/controles, decisões criptográficas, revisão de chaves e evidências dos quatro pilares; riscos residuais e aprovações necessárias.


## 8. Regras v0.3 a v0.5 que todos os agentes devem obedecer

- `Pendente` é OS não finalizada sem técnico; `Aberto` é legado.
- Reagendar `Pausado` é proibido até o fim da volta e transição para `Aguardando Reagendamento`.
- Conflito offline incompatível leva OS não finalizada para `Pendente` sem técnico, com auditoria.
- Custos são globais e o snapshot é obrigatório na finalização.
- Sessão offline dura até 24 h e não usa refresh token.
- Bucket de arquivos é privado; imagens até 15 MB; frontend não acessa Storage diretamente.
- Ajudantes e notificações estão fora do escopo.
- **RN-08a resolvida (07/11/2026):** desativar técnico desatribui todas as OS não finalizadas e não canceladas → `Pendente`, sem técnico, com histórico preservado e auditoria em `log_acao`; Finalizadas/canceladas não mudam.
- Toda OS que entra em `Agendado` ganha visita aberta na mesma transação; o administrador não recebe OS (só `tecnico`).
- Foto de conserto: menor lado ≥ 960 e maior lado ≥ 1280, em qualquer orientação. Tempo de serviço de visita pausada conta zero no custo.
- CPF/CNPJ do técnico com máscara canônica (14/18); CPF do cliente na visita só dígitos (11).
- Dev e produção compartilham o mesmo projeto Supabase (risco aceito pelo PO; Security mantém a ressalva). Não declarar SEG-xx como verificado com base apenas em testes SQLite.
- **Equipamento da OS (v0.5, confirmado em 08/11/2026; backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 414 testes automatizados em SQLite (v0.6, 09/11/2026) e um smoke ponta a ponta da v0.5 (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), seguidas das migrações `0010` a `0013` da v0.6. Entre 09 e 11/11/2026 o backend foi executado contra esse PostgreSQL, o painel web foi aberto no navegador e o app do técnico foi usado contra o backend nas verificações manuais de segurança registradas na SDD v0.6.1 (RLS, TLS `verify-full`, storage privado, JWT adulterado, hash de upload, selo da visita e cifra adulterada); a suíte de regras de negócio ainda não foi repetida contra o PostgreSQL):** o técnico não cadastra nem edita equipamento, modelo ou série; o admin mantém o catálogo de modelos e vincula modelo + série na OS (um ou mais). Toda OS tem ao menos um equipamento (OS sem equipamento não é criada). Atendimento só inicia com foto de defeito por equipamento e só finaliza com conserto salvo + foto de conserto por equipamento (409), a cada visita; pausa dispensa. Admin edita equipamento só até o início do atendimento e, com a OS Finalizada, apenas fotos comprobatórias e materiais (auditado; o custo é recalculado com os valores congelados). Renomear modelo reescreve o histórico exibido. Contrato em SDD 4.8, 4.9, 6.6, 6.7 e 6.13.
- Mudança de equipamento/série/foto/material passa por PO (regra), DBA (migração 0007 com `is_legado`), Backend (travas no serviço, não no router), Frontend (somente leitura no app; telas do painel) e QA (T-37 a T-59), na ordem da seção 3 "Feature com alteração de banco".
