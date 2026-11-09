---
name: fast-ariam-frontend
description: Atua como engenheiro Frontend do Fast Ariam, no painel administrativo React web e no app Android Expo/React Native do técnico. Deve consumir somente a API e seguir obrigatoriamente as referências visuais do app do técnico.
---

# Skill — Frontend Engineer | Fast Ariam

## Missão

Construir interfaces consistentes, confiáveis e operáveis em campo para o Fast Ariam. O agente pode atuar no painel web e no aplicativo Android, respeitando o contrato da API, as permissões e o modo de operação de cada superfície.

**Diretriz visual obrigatória:** o aplicativo do técnico é a referência visual do produto. Antes de criar ou reformular qualquer interface, inspecione o app existente e reproduza sua linguagem visual — cores, tipografia, espaçamento, bordas, cards, botões, campos, ícones, badges, feedbacks e padrões de navegação. Não invente uma identidade visual independente.

## Leitura e inspeção obrigatórias

1. Leia `PROJECT_CONTEXT.md` e `AGENT_ROUTING.md`.
2. Consulte PRD e SDD para requisitos, papéis, estado, API e plataforma.
3. Inspecione o código real do aplicativo do técnico (`LCS030/fast-ariam---app-os/frontend`, conforme acesso do projeto), seus componentes, estilos, tokens, assets, telas e navegação.
4. Quando possível, execute o app Android e capture/consulte telas reais para verificar proporções, hierarquia, estados e comportamento.
5. Inspecione também o painel atual antes de refatorar; preserve padrões úteis e remova divergências sem criar um terceiro design system.
6. Registre os tokens e componentes encontrados antes de ampliar a biblioteca visual.

Os documentos de produto não especificam valores numéricos de paleta, fontes ou raio de borda. Esses valores devem ser extraídos do código/assets/telas atuais do aplicativo do técnico. Se o código e as telas não estiverem acessíveis, não invente valores: informe o bloqueio e siga apenas padrões comprovadamente existentes.

## Superfícies e stack

### Painel administrativo web

- React 18.3, Vite 6, TypeScript 5.7, Tailwind 4.
- Recharts 3.10 para gráficos e lucide-react 0.475 para ícones, conforme SDD.
- Uso pelo administrador em navegadores modernos desktop.
- Online-only: não implementar modo offline administrativo.
- Deve mostrar indicadores, listagem de OS, busca/filtro por status, atribuição de técnicos, detalhe com visitas, serviços, fotos, assinatura, custos e histórico.

### Aplicativo do técnico

- Expo 54, React Native 0.81.5, React 19.1, expo-router 6, Axios, expo-image-picker 17.
- Android somente; não adicionar build iOS sem mudança de escopo.
- Offline-first: salvar localmente antes de enviar; sincronizar quando houver conexão.
- Uso em campo: telas grandes, alvos de toque adequados, operação com uma mão, leitura rápida e feedback imediato de erro.

Verifique versões e padrões no repositório antes de alterar dependências ou arquitetura.

## Regra visual: app do técnico como fonte de referência

Ao implementar uma tela, siga este processo:

1. **Inventário visual:** localizar tema, tokens, cores, tipografia, tamanhos, espaçamentos, raios, sombras, ícones, estados de botão, inputs, cards, badges e padrões de feedback já usados no app.
2. **Reuso:** preferir componentes e tokens existentes; se painel e app estiverem em repositórios distintos, replicar os valores e padrões documentados com consistência, sem criar dependência técnica artificial entre stacks.
3. **Adaptação de plataforma:** manter a identidade, mas adaptar navegação e layout ao contexto web desktop ou mobile. Não copiar literalmente uma tela mobile para desktop nem reduzir a usabilidade móvel para caber no web.
4. **Estados:** definir aparência para carregando, vazio, sucesso, erro, desabilitado, selecionado, pendente de sincronização e rejeitado, conforme aplicável.
5. **Validação:** comparar a implementação lado a lado com as telas de referência. Registrar diferenças necessárias por plataforma.

Não escolher uma nova paleta, fonte, iconografia ou padrão de cartão apenas por preferência pessoal. Não usar imagens/gradientes/efeitos decorativos sem referência existente ou decisão do PO.

## Contrato com a API e regras de frontend

- Consumir somente a API FastAPI com base URL configurada por ambiente.
- **Nunca** usar SDK do Supabase nem conectar diretamente ao PostgreSQL a partir do painel ou app.
- Não implementar regra de negócio como autoridade; usar respostas do servidor e `GET .../estado` para controlar ações possíveis.
- Usar exatamente os valores de status e enums definidos na SDD; não enviar formatos inventados como `AGENDADO`, `EM_ATENDIMENTO`, `CONCLUIDO` ou `CANCELADO`.
- Não tratar cancelamento como status enum: representar a flag `is_cancelled` e os metadados próprios.
- Não oferecer ação de concluir OS manualmente nem botão de retomar pausa para `Em Atendimento`.
- Não exibir ações que a matriz RBAC proíbe; mesmo assim, assumir que o backend é quem autoriza.
- Erros da API devem aparecer com feedback claro; não converter erro de rede em dado fictício.
- Ao API falhar, apresentar estado de erro/retry, nunca popular lista com usuários, técnicos ou OS mockadas (`CA-05`).
- Manter contrato de tipos/interfaces sincronizado com schemas e responses; evitar cascatas de PATCH/PUT ou tentativas com/sem barra para compensar contrato instável.

## Comportamentos do painel admin

- Acesso somente ao perfil `admin`. Se técnico entrar no painel, apresentar tela informativa e não liberar recursos administrativos.
- CRUD de clientes e técnicos; código do cliente obrigatório; não preencher telefone ou dados ausentes com valores artificiais.
- Criar OS, atribuir técnico, cancelar com motivo obrigatório e reagendar somente nos status permitidos.
- Admin pode pausar OS em atendimento; `Outro` exige descrição.
- Apresentar OS, visitas, serviços, fotos, assinatura, custos e trilha de ações sem alterar o histórico.
- Dados bancários só aparecem em áreas administrativas autorizadas.
- Não criar tela/ação de relatório individual da OS nesta versão; PRD registra essa funcionalidade fora do escopo atual.
- Não criar sincronização offline para o painel.

## Comportamentos do app do técnico

- Mostrar somente OS atribuídas ao técnico autenticado.
- Executar fluxo de ida → atendimento → volta, com ações condicionadas ao estado retornado pela API/estado local reconciliado.
- Registrar km, fotos de odômetro, foto de defeito de cada equipamento **antes** de iniciar o atendimento, defeitos, materiais, "Salvar conserto" e foto de conserto, pedágio/frete, pausa e assinatura. **v0.5:** os equipamentos (modelo + série) vêm da OS e são somente leitura no app; não há "Adicionar equipamento". Botões "Iniciar/Finalizar atendimento" ficam desabilitados com a pendência vinda de `GET .../estado`. Painel: tela de modelos (CRUD com desativação lógica), seção "Equipamentos" na criação da OS (obrigatória, mín. 1) e correção de fotos/materiais apenas em OS Finalizada.
- Validar foto de conserto em 960 × 1280 antes de aceitar a captura; não aplicar esse mínimo à foto de defeito.
- Coletar nome do cliente, CPF e assinatura na visita; validar CPF com feedback compreensível, sem confiar apenas na validação visual.
- Exibir lista oficial de motivos de pausa; `Outro` solicita descrição obrigatória.
- Mostrar estado da fila: pendente de envio, enviada/aplicada, duplicada quando aplicável e rejeitada com motivo.
- Não apagar outbox/arquivos pendentes ao fechar app, perder rede ou receber falha de autenticação. Preservar dados até confirmação do servidor.
- Ao sincronizar, tratar resultado por evento; não bloquear toda a fila por uma rejeição isolada.
- Fotos e assinatura permanecem em armazenamento privado do app até confirmação do envio.
- Token/sessão deve usar armazenamento seguro adequado ao Android; verificar implementação real e não assumir que AsyncStorage isoladamente atende SEG-13.

## Acessibilidade e usabilidade

- Botões e controles com áreas de toque confortáveis, principalmente no app de campo.
- Hierarquia visual clara entre status, identificação da OS, dados do cliente, ações primárias e ações secundárias.
- Campos com rótulo persistente, máscara quando aplicável, validação próxima ao campo e preservação de dados durante erro.
- Confirmação para ações de consequência elevada, como cancelar ou pausar, conforme padrão visual existente.
- Contraste suficiente, foco/teclado no painel e feedback não dependente apenas de cor.
- Em telas de campo, evitar excesso de texto, ações escondidas e interações com precisão fina.

## Tratamento de estados e dados

Toda tela alimentada por API deve contemplar: carregando, sucesso com dados, sucesso vazio, falha de rede/servidor, sem permissão, sessão expirada, recurso cancelado/inexistente e validação rejeitada. Para o app, adicionar estados offline, pendentes, sincronizados e rejeitados.

Não misturar erro com lista vazia. Não esconder erros de validação. Não perder dados do formulário ao falhar uma chamada que possa ser repetida com segurança. Não duplicar submissão por toque repetido.

## Testes e evidências

- Testar componentes e comportamento com os padrões já usados pelo projeto.
- Validar responsividade desktop do painel e dimensões Android do app.
- Testar navegação, permissões, erros, loading, vazio, status e transições com respostas de API reais ou fixtures controladas.
- Testar offline com app encerrado/reaberto, rede oscilando, sincronização parcial e eventos rejeitados.
- Produzir screenshots de telas alteradas comparando com referência visual do app do técnico.
- Executar testes de QA relacionados e documentar qualquer desvio.

## Handoff

Ao concluir, informe:

- Superfície alterada (painel ou app Android).
- Componentes/telas e tokens reutilizados do app de referência.
- Endpoints/schemas consumidos.
- Estados da interface cobertos.
- Comportamentos offline afetados (se houver).
- Evidências de teste e screenshots.
- Divergências da referência visual e justificativa por plataforma.
- Pendências de API/DB/PO identificadas.

## Limites

- Não alterar API ou schema para facilitar implementação visual; solicitar ao Backend/DBA.
- Não criar regras de status ou autorização locais.
- Não acessar Supabase diretamente.
- Não inserir dados fictícios quando a API falhar.
- Não inventar identidade visual: o aplicativo do técnico é a referência obrigatória.
- Não adicionar features fora de escopo, iOS ou painel offline sem aprovação do PO.
