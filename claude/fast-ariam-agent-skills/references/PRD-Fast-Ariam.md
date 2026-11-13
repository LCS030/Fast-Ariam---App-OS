# PRD — Fast Ariam: Gestão de Ordens de Serviço

| Campo | Valor |
|---|---|
| Produto | Fast Ariam (FAST Gôndolas & Check-outs) |
| Versão | 0.5 (regra de equipamento da OS de 08/11/2026 incorporada sobre a v0.4 de 07/11/2026) |
| Data | 08/11/2026 |
| Fontes analisadas | Backend: `LCS030/fast-ariam---app-os/backend` · App mobile técnico: `LCS030/fast-ariam---app-os/frontend` · Painel admin: `Jonathan-Ferreira-Berdusco/Fast-IA-Studio` |
| Documento irmão | `SDD-Fast-Ariam.md` (especificação técnica) |

> **v0.5 (08/11/2026):** incorpora a nova regra de negócio do responsável sobre **equipamentos da OS** (seção 6.10 e 11.1.2): o técnico deixa de cadastrar equipamento; o administrador mantém um catálogo de modelos e vincula modelo + número de série na OS; o atendimento só inicia com a foto do defeito e só finaliza com o conserto salvo e a foto do conserto. O responsável confirmou em 08/11/2026 as interpretações do detalhamento (seção 11.1.2, incluindo a correção administrativa de fotos e materiais após a finalização, RN-49); confirmou também que a correção de materiais **recalcula o custo** e que somente fotos e materiais são editáveis após a finalização. Não restam pontos em aberto sobre a regra de equipamento.

> **Atualização de situação (11/11/2026):** a camada de confidencialidade e integridade da v0.6 (cifragem AES-256-GCM de dados sensíveis e da assinatura, SHA-256 dos arquivos, selo HMAC-SHA256 da visita, TLS `verify-full`, RLS e Storage privado) está implementada e foi verificada manualmente no Supabase real entre 09 e 11/11/2026. As regras de negócio deste PRD não mudaram; o detalhamento técnico e as evidências estão na SDD v0.6/v0.6.1.

> **Atualização de situação (12/11/2026):** a proteção dos dados pessoais em repouso (RNF-02) foi ampliada no código: passam a ser cifrados o contato principal do cliente (nome e telefone), o nome de quem assina a visita e o nome e o CPF do cliente gravados no histórico de sincronização; o telefone comercial do cliente e os demais dados cadastrais continuam em claro (lista em RNF-02). Situação: **implementado e coberto por testes automatizados em SQLite** (suíte do backend: 526 passando e 2 falhas esperadas registradas, eram 414); a **migração do banco (`0014`) ainda não foi aplicada**, o script de cifragem dos dados existentes **não foi executado** em banco real e **nada foi verificado em PostgreSQL/Supabase**; os dados já gravados continuam em claro até a janela de execução. **Nenhuma regra de negócio mudou** (RN-22, RN-23 e RN-25 permanecem como estão); detalhes técnicos, riscos residuais e pendências na SDD v0.7.

> Este PRD foi escrito por engenharia reversa do código existente e revisado na v0.3 com as decisões complementares de negócio recebidas em 29/10/2026. As decisões confirmadas estão consolidadas na seção 11.1. A v0.4 (07/11/2026) incorpora as decisões do PO da seção 11.1.1; com elas a RN-08a deixa de ser pendência e **não há decisão de negócio bloqueante em aberto** (as pendências técnicas remanescentes estão na seção 11.2). Propostas antigas da v0.2 foram substituídas pelas decisões desta versão; o código atual continua sendo evidência de implementação, não a fonte de verdade do comportamento.

---

## 1. Visão geral

O Fast Ariam é um sistema para gerenciar Ordens de Serviço (OS) de manutenção de gôndolas e equipamentos de refrigeração em clientes. Ele é composto por três partes que compartilham o mesmo backend e o mesmo banco de dados:

- **Painel administrativo (web):** usado pelo escritório para cadastrar clientes, técnicos e modelos de equipamento, abrir OS com os equipamentos a consertar (modelo + número de série), atribuir técnicos, reagendar, cancelar e acompanhar custos.
- **Aplicativo do técnico (mobile):** usado em campo para executar a visita, registrar deslocamento, defeitos, conserto, materiais, fotos, pausas e assinatura do cliente sobre os equipamentos que **já vêm na OS** (o técnico não cadastra nem edita equipamento).
- **API (FastAPI):** única camada que acessa o banco. Os dois fronts não acessam o Supabase diretamente.

## 2. Problema

O problema de negócio foi confirmado pelo responsável: a operação da empresa dependia de registros manuais para acompanhar o atendimento em campo, os deslocamentos, a quilometragem, os comprovantes e os custos. Essa falta de padronização dificultava a comprovação dos serviços, a apuração dos valores e o acompanhamento centralizado das OS.

O Fast Ariam foi concebido para resolver esse problema, centralizando o ciclo de vida das OS e padronizando os registros do atendimento administrativo e de campo.

## 3. Objetivos e métricas

As metas abaixo são metas iniciais de produto. Devem ser acompanhadas após a entrada em operação e revistas com base na linha de base real da empresa.

| # | Objetivo | Métrica | Meta inicial |
|---|---|---|---|
| O1 | Registrar todas as visitas com deslocamento rastreável | % de visitas encerradas com km e horários de ida e volta válidos | 100% |
| O2 | Comprovar o atendimento | % de OS finalizadas com nome, CPF válido e assinatura; e fotos exigidas quando aplicáveis | 100% de assinatura e dados válidos. **Desde a v0.5:** 100% das OS criadas após a mudança têm foto de defeito e foto de conserto de cada equipamento (garantido pelo sistema, RN-43/RN-44). A meta de ≥ 95% de evidências fotográficas aplica-se somente às OS legadas, que não passam por essas travas |
| O3 | Calcular o custo de cada OS automaticamente | % de OS finalizadas com custo calculado e snapshot persistido, sem ajuste manual | 100% |
| O4 | Formalizar pausas e reagendamentos | % de OS em Aguardando Reagendamento para as quais o administrador agenda nova visita em até 2 dias úteis | ≥ 90% |
| O5 | Permitir o registro da visita sem internet | % de eventos/arquivos offline contabilizados após sincronização, sem perda silenciosa ou duplicidade | 100% contabilizados; 0 duplicidades |
| O6 | Manter um único conjunto de regras entre painel, app e API | Divergências críticas/altas de contrato abertas no momento de release | 0 |

Para O4, o prazo é contado a partir da entrada da OS em **Aguardando Reagendamento** até o registro do novo agendamento. Para O5, um evento pode ser aplicado ou rejeitado com motivo; o objetivo de 100% contabilizados não significa que toda ação conflitante deva ser aceita.

## 4. Personas

| Persona | Quem é | Principais necessidades |
|---|---|---|
| **Administrador** | Equipe do escritório (conta com papel `admin`) | Cadastrar clientes, técnicos e modelos de equipamento; abrir OS já com os equipamentos (modelo + série) e atribuir; reagendar; cancelar; ver custos e relatórios |
| **Técnico de campo** | Técnico cadastrado (papel `tecnico`), pode ser pessoa jurídica | Ver só as próprias OS e os equipamentos delas (somente leitura); executar o fluxo de visita; registrar fotos de defeito e de conserto, defeitos, materiais e pausas; colher assinatura |
| **Cliente** | Empresa atendida (não usa o sistema) | Assinar a OS; ter comprovação do atendimento |

## 5. Escopo

**Dentro do escopo (estado atual do código):**
- Login com e-mail e senha, troca de senha pelo próprio técnico
- CRUD de clientes e técnicos (desativação lógica)
- Ciclo de vida da OS: criar, atribuir, cancelar, reagendar, concluir
- Visitas, deslocamento de ida e volta, atendimento, pausa
- Catálogo de modelos de equipamento (admin) e vínculo de um ou mais equipamentos (modelo + número de série) a cada OS (seção 6.10)
- Correção administrativa, em OS Finalizada, de fotos comprobatórias e de materiais utilizados, com auditoria (RN-49)
- Defeitos, conserto e materiais registrados pelo técnico sobre os equipamentos da OS
- Fotos de defeito, de conserto, de odômetro e de deslocamento
- Comprovantes de pedágio e frete
- Assinatura digital do cliente
- Cálculo e registro de custos por OS, com valores de referência centralizados na configuração do sistema (apenas registro interno, sem cobrança ao cliente)
- Registro offline da visita no aplicativo por até 24 horas sem conexão, com sincronização posterior com o banco
- Upload de imagens JPEG/PNG com limite máximo de 15 MB por arquivo e armazenamento persistente em bucket privado

**Fora do escopo (nesta versão):**
- Faturamento, emissão de nota fiscal e pagamento aos técnicos (o sistema apenas armazena os dados bancários)
- Notificações push, e-mail ou WhatsApp (decisão confirmada: não são necessárias nesta versão)
- Cadastro, acompanhamento e cálculo de custo de ajudantes (fora do escopo desta etapa)
- Ficha técnica do modelo (fabricante, capacidade, foto), histórico por número de série entre OS ("parque de equipamentos"), leitura por QR/código de barras, importação em lote de modelos e pedido de correção de série pelo técnico (v0.5)
- Relatório da OS (decisão de 29/10/2026: não é necessário no momento)
- Cobrança do cliente com base no custo calculado
- Aplicativo para iOS (a versão atual é somente Android)
- Painel administrativo offline (apenas o app do técnico opera offline)
- Multi-empresa (tenant)
- Gestão de estoque de peças

## 6. Requisitos funcionais

Convenção: **RF** = requisito funcional, **RN** = regra de negócio. Os códigos são referenciados na SDD.

### 6.1 Autenticação e acesso

- **RF-01** O usuário entra com e-mail e senha e recebe um token de acesso (JWT), que expira em 30 minutos por padrão (configurável).
- **RF-02** Há dois papéis. `admin` acessa o painel web. `tecnico` acessa o aplicativo mobile.
- **RF-03** Se um técnico entrar no painel web, o painel mostra uma tela informativa e não libera o acesso administrativo.
- **RF-04** O técnico troca a própria senha informando a senha atual.
- **RN-01** Usuário desativado não consegue entrar.
- **RN-02** Senhas são armazenadas apenas como hash (bcrypt).

### 6.2 Clientes (admin)

- **RF-05** Cadastrar, listar (ativos, inativos ou todos), editar e desativar clientes.
- **RF-06** Campos: razão social, código, contato principal (nome e telefone), telefone, endereço, número, bairro, cidade e UF.
- **RN-03** Clientes desativados não recebem nova OS.
- **RN-04** O campo `codigo` é obrigatório, único e informado manualmente pelo administrador. Ele vem de outro sistema, sem integração no momento. Hoje o schema aceita cliente sem código e o banco rejeita (PR-27).
- **RN-05** A exclusão de cliente é lógica. O cliente continua existindo para as OS já vinculadas.

### 6.3 Técnicos (admin)

- **RF-07** Cadastrar, listar, editar e desativar técnicos.
- **RF-08** Campos: nome, CNPJ, CPF, inscrição estadual, e-mail, telefone, papel, dados bancários (banco, agência, conta e Pix) e senha.
- **RN-06** CNPJ e e-mail são únicos entre técnicos. CPF e CNPJ do técnico são armazenados com **máscara canônica** (CPF `000.000.000-00`, 14 caracteres; CNPJ `00.000.000/0000-00`, 18 caracteres), de modo que a unicidade do CNPJ não dependa da forma como foi digitado. (O CPF do **cliente** informado na assinatura da visita é diferente: fica só com dígitos, 11 caracteres, ver RN-23.)
- **RN-07** Os dados bancários são obrigatórios no cadastro (banco, agência e conta). Pix é opcional. **Somente o administrador altera os dados bancários**; o técnico não os altera.
- **RN-08** Técnico desativado não pode ser atribuído a nova OS. **O administrador também não pode receber OS**: somente usuários com papel `tecnico` (e ativos) são atribuíveis.
- **RN-08a [RESOLVIDA em 07/11/2026]** Ao desativar um técnico, o sistema **desatribui automaticamente TODAS as OS dele não finalizadas e não canceladas** (`Agendado`, `Em Atendimento`, `Pausado` e `Aguardando Reagendamento`), que passam para **Pendente**, sem técnico, na mesma operação da desativação. Visitas, fotos, serviços e pausas são **preservados como histórico** (pausas ativas são encerradas, sem perder o registro). OS **Finalizadas** e **canceladas** não mudam. A ação é **auditada** em `log_acao`. Quando o administrador reatribuir a OS depois, se havia visita iniciada pelo técnico anterior, essa visita permanece como histórico e é criada uma **visita nova** para o novo técnico (RN-11a).
- **RN-09** Técnico desativado perde o acesso ao aplicativo na requisição seguinte, mesmo com token ainda válido. Implementado no backend na v0.4 (PR-05, ver 9.2); verificado apenas por testes em SQLite.

### 6.4 Ordem de Serviço (OS)

- **RF-09** O administrador cria uma OS para um cliente ativo, com a descrição do problema e **ao menos um equipamento a consertar (modelo do catálogo + número de série)**, conforme a seção 6.10. Pode atribuir um técnico já na criação.
- **RN-10** Se a OS nasce com técnico, o status inicial é **Agendado**. Se não, o status inicial é **Pendente**. O status `Aberto` fica obsoleto e deve ser eliminado do fluxo novo por migração controlada.
- **RF-10** O administrador atribui ou troca o técnico de uma OS.
- **RN-11** Ao atribuir técnico sem informar status, a OS passa para **Agendado**.
- **RN-11a** Toda OS que entra em **Agendado** (criação com técnico, atribuição a uma OS `Pendente`, reagendamento) ganha uma **visita aberta na mesma transação**. `data_visita` = `data_agendamento` ou, se vazia, a **data de hoje no fuso `America/Sao_Paulo`**. Não é possível criar outra visita enquanto houver visita não finalizada na OS. Em reatribuição após desativação de técnico (RN-08a), a visita iniciada pelo técnico anterior fica como histórico e é criada uma nova para o novo técnico.
- **RF-11** O administrador cancela a OS informando o **motivo, que é obrigatório**. O cancelamento é lógico: a OS fica marcada como cancelada, com motivo, data e autor, e some das listagens padrão.
- **RN-12** Pode-se cancelar uma OS em qualquer status, **inclusive Em Atendimento, Pausado e Pendente**, desde que ainda não esteja Finalizada e ainda não esteja cancelada. OS Finalizada ou já cancelada não pode ser cancelada novamente; a API deve retornar conflito. Ao cancelar, as pausas ativas são encerradas e o técnico deixa de ver a OS. O que ele já registrou fica guardado.
- **RF-12** O técnico vê somente as OS atribuídas a ele. Ele não vê OS de outros técnicos.
- **RN-13** O técnico **não altera o status da OS por edição direta** (nem o da própria OS) e não pode marcá-la como Finalizada; o status só muda pelas ações do fluxo da visita (seção 6.5). O administrador também não escolhe status arbitrário por edição da OS.
- **RF-13** O administrador reagenda a OS somente nos status **Aguardando Reagendamento** e **Agendado antes de o técnico iniciar o deslocamento de ida**. O reagendamento de uma OS em **Pausado** é proibido até que o técnico finalize o deslocamento de volta e a OS passe para **Aguardando Reagendamento**. Fora dos estados permitidos, a API recusa a operação.
- **RN-14** Reagendar uma OS **Aguardando Reagendamento** cria uma nova visita, encerra a pausa e leva a OS para **Agendado**. Uma OS **Pausado** não pode receber novo agendamento enquanto o técnico não finalizar o deslocamento de volta; ao finalizar a volta, a visita é encerrada e a OS passa para **Aguardando Reagendamento**. Reagendar uma OS **Agendado** com ida ainda não iniciada altera a data da visita existente, sem criar visita vazia.
- **RN-15** Uma OS pode ter **várias visitas**. Cada visita tem os seus próprios deslocamentos (ida e volta), atendimento, serviços, fotos, comprovantes e assinatura. Não se reagenda OS Finalizada ou Cancelada.
- **RF-14** A OS é concluída **automaticamente** ao finalizar o deslocamento de volta de uma visita sem pausa ativa. **Não existe conclusão manual**, nem pelo técnico nem pelo administrador.

### 6.5 Visita e execução em campo (aplicativo do técnico)

Fluxo normal, na ordem em que o técnico executa:

1. **Iniciar deslocamento de ida:** informa o km inicial e tira foto do odômetro.
2. **Finalizar deslocamento de ida:** informa o km final e tira foto do odômetro.
3. **Registrar a foto do defeito:** para **cada equipamento da OS** (modelo e número de série já vinculados pelo administrador, somente leitura), o técnico registra ao menos uma foto do defeito. *(v0.5: a foto do defeito passa a vir **antes** de iniciar o atendimento.)*
4. **Iniciar atendimento:** só é permitido com a foto do defeito de todos os equipamentos (RN-43). O horário é registrado e a OS passa para **Em Atendimento**.
5. **Registrar o conserto:** para cada equipamento da OS, informa defeitos (principal e sub-defeitos) e materiais usados, **salva o conserto** (RN-47) e tira a foto do conserto. O técnico **não cadastra equipamento** nem edita modelo ou número de série (RN-42).
6. **Finalizar atendimento:** só é permitido com o conserto salvo e a foto do conserto de todos os equipamentos (RN-44). Informa nome e documento do cliente e colhe a assinatura digital.
7. **Iniciar deslocamento de volta:** informa o km inicial e tira foto do odômetro.
8. **Finalizar deslocamento de volta:** informa o km final e tira foto do odômetro. Com isso a visita é encerrada e a OS passa para **Finalizado**.
9. Pedágio e frete são informados com comprovantes quando houver valor.

Regras:

- **RN-16** O botão seguinte só aparece quando a etapa anterior foi concluída. A tela consulta o estado da visita para decidir quais ações exibir. *(v0.5: "Iniciar atendimento" e "Finalizar atendimento" permanecem visíveis porém desabilitados, com a pendência exibida, enquanto RN-43/RN-44 não forem cumpridas.)*
- **RN-17** O atendimento só pode ser iniciado depois de finalizado o deslocamento de ida **e de registrada a foto do defeito de cada equipamento da OS na visita (RN-43)**. Na v0.4 o backend já recusava iniciar atendimento sem a ida finalizada (PR-36, ver SDD 6.6); a tela continua apenas consultando o estado, e o backend é a autoridade.
- **RN-18** O deslocamento de volta só pode ser iniciado depois de finalizado o atendimento, **exceto** quando a visita está pausada.
- **RN-19** Se o km total da visita for maior que zero, as fotos de odômetro de início e fim são obrigatórias para finalizar a visita.
- **RN-20** Se o valor de pedágio for maior que zero, o comprovante de pedágio é obrigatório. O mesmo vale para o frete de devolução.
- **RN-21** Somente as fotos de **conserto** precisam ter resolução mínima **equivalente a 960 × 1280 px em qualquer orientação** (retrato ou paisagem): o **menor lado deve ser ≥ 960 px e o maior lado ≥ 1280 px**. Fotos de defeito, odômetro e deslocamento não têm essa exigência (PR-29).
- **RN-22** A assinatura do cliente, o nome e o documento são obrigatórios para finalizar o atendimento, **somados às exigências de conserto da RN-44 (conserto salvo e foto do conserto de cada equipamento), que são verificadas antes de gravar a assinatura**. A assinatura pertence **à visita**, não à OS, porque uma OS pode ter várias visitas (PR-35).
- **RN-23** O documento do cliente é um **CPF** e deve passar por **validação de CPF** (formato e dígitos verificadores).
- **RN-24** Cada horário é registrado **no aparelho do técnico, no momento em que a ação ocorre**, com data, hora e fuso (`ocorrido_em`). Isso vale para o fluxo online e para o offline (seção 6.9). Nos endpoints online o `ocorrido_em` já é aceito (opcional; sem ele vale o instante do servidor; futuro acima de 5 minutos é recusado); a fila offline segue pendente (PR-30).
- **RN-25** Ajudantes não fazem parte do escopo desta etapa. Não implementar cadastro, campos de interface, gestão ou cálculo associado a ajudantes. Campos legados existentes podem ser preservados temporariamente para não perder dados históricos, sem uso em novas operações.
- **RN-42** *(v0.5)* O técnico **não cria, edita nem remove** equipamento, modelo ou número de série. Ele registra somente defeitos, conserto, materiais e fotos do equipamento já vinculado à OS pelo administrador. O backend recusa qualquer tentativa de enviar ou alterar esses campos.
- **RN-43** *(v0.5)* O atendimento **não pode ser iniciado** se, na visita, algum equipamento da OS ainda não tiver ao menos uma **foto de defeito**. O backend recusa com 409 e lista os equipamentos pendentes. A exigência vale **por equipamento da OS** (confirmado em 08/11/2026) e, como fotos e serviços pertencem à visita (RN-15), é verificada a cada visita.
- **RN-44** *(v0.5)* O atendimento **não pode ser finalizado** se, na visita, algum equipamento da OS não tiver o **conserto salvo** (RN-47) e ao menos uma **foto de conserto** (RN-21). O backend verifica no momento de finalizar, e não apenas no upload, e recusa com 409 listando as pendências. A exigência vale por equipamento da OS e é verificada a cada visita (confirmado em 08/11/2026).
- **RN-47** *(v0.5, confirmado em 08/11/2026)* **Conserto salvo** é uma marca explícita, gravada somente quando o técnico aciona "Salvar conserto" no equipamento, com ao menos um defeito principal informado. Materiais são opcionais. Apenas existir o registro de serviço do equipamento, criado para receber a foto do defeito, **não** conta como conserto salvo.

### 6.6 Pausa de OS

Objetivo (conforme `Fluxo Pausar OS.txt`): permitir que o técnico interrompa o atendimento quando não pode concluí-lo (falta de peça, cliente ausente, etc.), volte para casa e aguarde um novo agendamento.

Fluxo:

1. Durante o atendimento (após iniciá-lo e antes de finalizá-lo), o técnico toca em **Pausar OS**. O **administrador também pode pausar** a OS pelo painel.
2. Um modal pede o motivo (lista predefinida) e uma descrição opcional.
3. A OS passa para **Pausado**. O botão de finalizar atendimento some e o botão de concluir a visita é substituído pelo deslocamento de volta.
4. O técnico faz o deslocamento de volta (ida e volta de km e fotos, como no fluxo normal).
5. Ao finalizar o deslocamento de volta, a visita é encerrada e a OS passa para **Aguardando Reagendamento**. O técnico vê a mensagem de aguardando reagendamento.
6. O administrador agenda nova data. É criada uma nova visita, a OS volta para **Agendado** e a pausa deixa de aparecer.
7. O técnico executa a nova visita pelo fluxo normal.

Regras:

- **RN-26** Só é possível pausar uma visita que já está em atendimento e não foi finalizada.
- **RN-27** Enquanto a visita está pausada, o atendimento não pode ser finalizado.
- **RN-28** O técnico não pode reagendar. Somente o administrador reagenda.
- **RN-29** A lista oficial de motivos é a do aplicativo: **Peça pendente, Cliente ausente, Condições inseguras, Aguardando aprovação e Outro**. Ao escolher **Outro**, a descrição em texto livre é obrigatória. Nos demais, a descrição é opcional. App, painel e backend devem usar a mesma lista (PR-15).
- **RN-30** O administrador pode pausar uma OS, com as mesmas regras do técnico (RN-26 e RN-29): somente quando a visita estiver em atendimento e ainda não finalizada. O registro da pausa guarda quem pausou e com qual papel.
- **RN-48** *(v0.5)* A pausa **não exige** conserto salvo nem foto de conserto: o atendimento é interrompido justamente por não poder ser concluído. O deslocamento de volta de uma visita pausada leva a OS a **Aguardando Reagendamento** sem as exigências da RN-44, que só valem para finalizar o atendimento. Como só se pausa um atendimento já iniciado, a RN-43 (foto de defeito) sempre foi cumprida antes.

### 6.7 Painel administrativo (visualização e relatórios)

- **RF-15** Painel inicial com indicadores e gráficos das OS.
- **RF-16** Lista de OS com busca e filtro por status, e ação de atribuir técnico.
- **RF-17** Tela de detalhe da OS com **equipamentos (modelo e número de série)**, visitas, serviços, fotos, assinatura, custos e histórico de ações.
- **RF-18** *(Removido)* O relatório da OS não é necessário no momento. Se o componente `RelatorioOS` estiver acessível no painel, deve ser retirado da navegação.

### 6.8 Custos

- **RF-19** Cada OS tem um custo total calculado a partir das visitas. O custo considera: materiais (quantidade × valor), quilometragem, pedágio, frete, tempo de deslocamento e tempo de serviço.
- **RN-31** Tempo de serviço: até 1 hora cobra o valor da primeira hora; acima disso cobra a hora adicional proporcional. **O tempo de serviço de uma visita pausada conta ZERO no custo**, pois o atendimento não foi finalizado; deslocamento, quilometragem, pedágio, frete e materiais da visita continuam sendo considerados.
- **RN-32** Os valores de referência (primeira hora, hora adicional, tempo de deslocamento e quilometragem) são **centralizados na configuração do sistema**. O técnico não pode visualizar uma tela de configuração nem alterar esses valores. Não há configuração individual por técnico. Os valores são consumidos pelo backend no cálculo. A forma operacional de alterar esses parâmetros deve permanecer restrita à administração técnica do sistema; a versão atual não exige uma interface de edição para o técnico.
- **RN-33** O custo calculado **não é cobrado do cliente**. Ele é apenas registrado. Ao finalizar a OS, o sistema deve congelar o cálculo e os valores utilizados, preservando o histórico mesmo que a configuração global seja alterada posteriormente. Única exceção: a correção de materiais pelo administrador em OS Finalizada (RN-49) recalcula o custo, **reutilizando os mesmos valores de referência congelados**.

### 6.9 Operação offline (aplicativo do técnico)

O técnico precisa registrar a visita sem internet. Quando a conexão volta, os dados são enviados e gravados no banco.

- **RF-20** O técnico executa o fluxo da visita (6.5) e a pausa (6.6) sem conexão. Cada ação fica salva no aparelho.
- **RF-21** O app mostra o estado de cada ação: **pendente de envio**, **enviada** ou **rejeitada** (com o motivo).
- **RF-22** As OS atribuídas ao técnico ficam disponíveis para consulta no aparelho a partir da última sincronização.
- **RN-35** O horário de cada ação é o do momento em que ela ocorreu no aparelho, não o do envio (RN-24).
- **RN-36** Enviar a mesma ação mais de uma vez não pode duplicar registros.
- **RN-37** Fotos e assinatura também ficam em fila e são enviadas ao sincronizar. A foto de conserto é validada (RN-21) **no momento da captura**, para não ser rejeitada depois, quando o técnico já saiu do local.
- **RN-37a** *(v0.5)* Os equipamentos da OS (modelo e número de série) são baixados com a OS e ficam disponíveis para consulta offline. O app espelha localmente RN-43/RN-44 apenas como conveniência de tela: a foto do defeito é registrada antes do evento de início do atendimento, e o servidor decide. Evento de início ou de finalização que viole RN-43/RN-44 é rejeitado com motivo rastreável, sem apagar eventos nem arquivos locais (RN-38).
- **RN-38** Se a sincronização identificar conflito entre ações offline do técnico e uma alteração administrativa incompatível, o sistema não deve simplesmente descartar o conflito como se a ação administrativa tivesse resolvido toda a situação. As ações conflitantes são rejeitadas com motivo rastreável e a OS não finalizada passa para **Pendente**, sem técnico atribuído, para análise e nova atribuição pelo administrador. Eventos anteriores compatíveis podem ser aplicados conforme a ordem de ocorrência. Cancelamento e finalização já efetivados permanecem respeitados como estados terminais; arquivos e eventos locais não podem ser apagados silenciosamente.
- **RN-39** O primeiro login exige internet. Após autenticação online bem-sucedida, o técnico pode operar offline por até **24 horas**. Não haverá refresh token. O JWT permanece com expiração definida no backend; quando estiver expirado, o app preserva a fila local e exige autenticação online novamente para sincronizar. Ao ultrapassar 24 horas sem conexão, o app deve bloquear novas operações autenticadas até recuperar a conexão e autenticar novamente, sem apagar os dados pendentes.
- **RNF-09** Nenhum dado registrado offline pode ser perdido por falha de envio, fechamento do app ou queda de energia.

O painel administrativo continua exigindo conexão.

### 6.10 Equipamentos da OS (catálogo e vínculo) — novo na v0.5

Regra de negócio de 08/11/2026: o equipamento a consertar **já vem na OS**. O técnico não o cadastra.

**Catálogo de modelos (admin)**

- **RF-23** O administrador mantém o catálogo de modelos de equipamento: criar, listar, editar o nome e desativar/reativar. O modelo tem **apenas o nome**, por exemplo "Freezer vertical modelo X", "Freezer vertical modelo Y", "Freezer horizontal modelo X".
- **RN-40** O nome do modelo é obrigatório e **único**, comparado sem espaços nas pontas e sem diferenciar maiúsculas de minúsculas. Modelo vinculado a alguma OS pode ser **desativado, mas não excluído**. Modelo desativado não é oferecido em novos vínculos; as OS existentes mantêm o histórico. Renomear é permitido, é auditado e altera a exibição também no histórico (não há cópia do nome na v0.5).

**Vínculo na OS (admin)**

- **RF-24** Ao criar a OS, o administrador vincula **um ou mais equipamentos**, cada um com **modelo ativo do catálogo e número de série**. O administrador pode vincular mais de um equipamento na mesma OS, inclusive do mesmo modelo com séries diferentes.
- **RN-41** *(confirmado em 08/11/2026)* **Toda OS tem obrigatoriamente ao menos um equipamento vinculado; OS sem equipamento não podem ser criadas** (a API recusa a criação, 422). O número de série é obrigatório e **único dentro da OS** (sem diferenciar maiúsculas e sem espaços nas pontas); o mesmo número pode aparecer em OS diferentes. Não se remove o último equipamento da OS.
- **RN-45** *(confirmado em 08/11/2026)* O administrador pode **adicionar, corrigir e remover** equipamento da OS enquanto ela não estiver Finalizada nem cancelada **e a visita vigente ainda não tiver iniciado o atendimento**. Do início do atendimento até a finalização da OS a edição do equipamento é recusada (409), para não mudar o escopo sob o técnico em campo. Equipamento que já tenha foto, defeito, material ou conserto registrado em qualquer visita **não pode ser removido**. Toda alteração é auditada em `log_acao`. A edição **volta a ser possível somente quando a OS estiver Finalizada**, nos termos restritos da RN-49 (correção de fotos comprobatórias e de materiais; modelo e número de série continuam travados).
- **RN-46** **OS legada sem equipamento** (anterior à v0.5) é uma exceção transitória, a ser sanada pela migração e pelo administrador: enquanto não tiver ao menos um equipamento vinculado, ela **não pode ser atribuída, reagendada nem ter o atendimento iniciado**. OS Finalizadas ficam fora das novas regras e não são alteradas (exceto pela correção da RN-49).
- **RN-49** *(v0.5, confirmado em 08/11/2026)* **Correção administrativa de OS Finalizada.** Somente quando a OS está **Finalizada** (não cancelada), o administrador pode corrigir **fotos comprobatórias** (defeito e conserto: enviar nova foto ou remover, mantendo ao menos uma foto de cada tipo por equipamento atendido) e **materiais utilizados** dos equipamentos, em qualquer visita da OS. O técnico não tem essa permissão. Valem as mesmas validações de imagem (JPEG/PNG, 15 MB, 960 × 1280 em qualquer orientação para conserto). Toda correção é auditada em `log_acao` (quem, quando, o que mudou). **Somente fotos e materiais são passíveis de edição após a finalização:** a correção não altera modelo, número de série, defeitos, conserto salvo, assinatura, quilometragem, horários nem o status. **A correção de materiais recalcula o custo da OS** (decisão do responsável em 08/11/2026): o novo total é calculado com os materiais corrigidos e com os **mesmos valores de referência congelados na finalização** (primeira hora, hora adicional, deslocamento e quilometragem), de modo que mudanças posteriores na configuração global continuem sem afetar o histórico (RN-33); o snapshot de custo é substituído e o total anterior e o novo ficam registrados em `log_acao`.

**Técnico (app)**

- **RF-25** O app exibe os equipamentos da OS (modelo e número de série) **somente para leitura**; sobre eles o técnico registra foto de defeito, defeitos, materiais, conserto e foto de conserto (RN-42 a RN-44, RN-47).
- As exigências de foto e de conserto valem **por equipamento e por visita** (RN-15): em uma segunda visita (após reagendamento) o técnico registra novamente a foto de defeito e o conserto. O equipamento em si pertence à OS e é compartilhado entre as visitas.

## 7. Modelo de status da OS

| Status | Significado | Quem altera | Gatilho |
|---|---|---|---|
| Pendente | OS criada, não finalizada e sem técnico atribuído | Sistema/admin por meio das operações de criação, atribuição, desativação de técnico ou resolução de conflito offline | Criação sem técnico, desativação do técnico atribuído (RN-08a) ou conflito offline que exija retirar a atribuição |
| Agendado | OS com técnico ativo atribuído e data prevista | Sistema, após atribuição ou reagendamento pelo admin | Atribuir técnico ou reagendar |
| Em Atendimento | Técnico iniciou o atendimento após finalizar a ida | Sistema | Iniciar atendimento |
| Pausado | Visita em atendimento interrompida formalmente | Técnico ou admin | Pausar OS durante atendimento |
| Aguardando Reagendamento | Visita pausada encerrada após a volta; aguarda nova data | Sistema | Finalizar deslocamento de volta com pausa ativa |
| Finalizado | Atendimento concluído | Sistema | Finalizar deslocamento de volta sem pausa ativa |
| Cancelado | OS cancelada | Admin | Marcação lógica `is_cancelled`, não é valor do enum |

`Aberto` é um status legado e não deve ser usado em novas OS. A migração deve converter OS legadas `Aberto` sem técnico para `Pendente`. Registros legados `Pendente` que tenham técnico atribuído devem ser inventariados e tratados antes da migração, pois o significado de `Pendente` foi redefinido nesta versão.

Transições principais:

```text
(criação sem técnico) ──► Pendente ──(atribuir técnico)──► Agendado
                                                       │
                                                       ▼
                                                Em Atendimento
                                                  │       │
                                       (pausar)    │       │ (volta sem pausa)
                                                  ▼       ▼
                                                Pausado  Finalizado
                                                  │
                                      (finalizar volta com pausa)
                                                  ▼
                                      Aguardando Reagendamento
                                                  │
                                      (reagendar pelo admin)
                                                  ▼
                                               Agendado
```

Regras:

- `Pendente` é reservado a OS não finalizada sem técnico atribuído; não significa serviço tecnicamente pendente durante um atendimento.
- Quando um conflito de sincronização exigir colocar a OS em `Pendente`, a atribuição do técnico é removida e a decisão fica registrada para análise do administrador.
- `Pausado` não pode ser reagendado. O técnico deve finalizar a volta; a OS passa para `Aguardando Reagendamento` e só então o administrador pode agendar nova visita.
- `Finalizado` só é alcançado pelo fim do deslocamento de volta sem pausa ativa. Não há conclusão manual.
- `Cancelado` não é status enum; é uma marca `is_cancelled` com motivo obrigatório. OS Finalizada ou já cancelada não pode ser cancelada novamente.
- A desativação de técnico leva **todas** as suas OS não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) a `Pendente`, sem técnico, preservando o histórico e auditando a ação (RN-08a, resolvida em 07/11/2026). OS Finalizadas e canceladas não mudam.

## 8. Requisitos não funcionais

- **RNF-01 Segurança:** autenticação por JWT, senhas com bcrypt, controle de acesso por papel em todas as rotas, segredo em variável de ambiente, HTTPS em produção.
- **RNF-02 Dados pessoais (LGPD):** o sistema guarda nome, documento, telefone e dados bancários. Decisão atual: fotos e dados pessoais são **mantidos sem data de exclusão**. Isso precisa de acesso mínimo, armazenamento privado e backup, e deve ser revisto quando houver uma política de retenção.
  - **Situação em 12/11/2026 (atualização de situação; sem mudança de regra).** *Cifrado em repouso pela aplicação (AES-256-GCM):* CPF do cliente na visita; **nome de quem assina a visita**; **contato principal do cliente (nome e telefone)**; **nome e CPF do cliente no histórico de sincronização offline**; CPF, CNPJ, telefone e dados bancários/PIX do técnico; e a imagem da assinatura. *Em claro (risco residual aceito):* telefone comercial do cliente, razão social, endereço, cidade, UF e código do cliente; e-mail, nome e inscrição estadual do técnico; textos livres (descrições, pendências, observações); demais campos do histórico de sincronização; fotos e comprovantes (só a cifra da plataforma de armazenamento); campos legados de ajudante (fora do escopo, RN-25). *Limites:* a cifragem protege o dado no servidor; **não** cobre a fila e o cache do aplicativo no aparelho (em claro até a sincronização), os backups e o histórico do provedor (podem conter o dado em claro), nem quem controla o servidor e as chaves; perder a chave de cifragem torna os dados cifrados irrecuperáveis. *Estado:* implementado e testado apenas em SQLite; a migração `0014` e a cifragem dos dados já existentes aguardam a janela de execução; nada foi verificado em PostgreSQL/Supabase. Detalhes e riscos residuais: SDD v0.7, seções 8 e 8.1.
- **RNF-03 Rastreabilidade:** o sistema deve registrar quem fez cada ação (criação, atribuição, pausa, finalização). **Hoje isso é parcial** (ver PR-20).
- **RNF-04 Armazenamento de arquivos:** fotos, comprovantes e assinaturas devem ser persistentes em bucket privado do Supabase Storage, acessíveis somente após autorização da API por URL assinada de curta duração. O limite é 15 MB por imagem/arquivo de imagem. O uso deve respeitar as cotas do plano contratado. *(v0.6, 09/11/2026: implementado com bucket privado; a API entrega o arquivo pelas próprias rotas autenticadas, após autorizar o acesso à OS, sem emitir URL assinada.)*
- **RNF-05 Desempenho:** em ambiente de homologação com até 20 usuários simultâneos e base de teste com até 1.000 OS ativas/históricas consultáveis, listagens e detalhes de OS devem responder em p95 ≤ 2 segundos (excluindo transferência de arquivos). Upload de imagem de 15 MB deve concluir em até 30 segundos em conexão estável com upload de 10 Mbps, excluindo indisponibilidade da rede móvel externa.
- **RNF-10 Sessão offline:** até 24 horas desde a última autenticação online bem-sucedida, sem refresh token; após o limite, exigir reconexão e novo login, preservando a fila local.
- **RNF-06 Usabilidade em campo:** telas grandes, botões que funcionam com uma mão, feedback imediato de erro.
- **RNF-07 Plataformas:** o app roda **somente em Android**. Web do painel: navegadores modernos em desktop.
- **RNF-08 Operação:** o servidor precisa de um procedimento de deploy e de migração de schema (hoje não há migrações, ver PR-19).

## 9. Diagnóstico do estado atual

Problemas encontrados ao cruzar os três projetos. Severidade: **Crítica** (quebra fluxo ou risco de dado errado), **Alta** (impede um requisito), **Média** (dívida ou risco latente), **Baixa** (higiene).

| ID | Severidade | Área | Problema | Evidência |
|---|---|---|---|---|
| PR-01 | Crítica | Painel | O botão de "reparar perfil", exibido quando há erro de validação, envia ao técnico de id 1 um perfil fixo com nome, CPF, e-mail e dados bancários genéricos. Isso **sobrescreve o cadastro real**. | `apiClient.repairTecnicoProfile`, usado em `AdminDashboardView` |
| PR-02 | Crítica | Painel | Quando a API falha, a lista de técnicos é preenchida com usuários fictícios. O administrador pode atribuir OS a um técnico que não existe. | `apiClient.getTecnicos`, bloco `fallbackList` |
| PR-03 | Crítica | Backend | Fotos e assinaturas são gravadas em disco local (`static/uploads`, `static/assinaturas`). Em hospedagem sem disco persistente, os arquivos se perdem. A URL é relativa e só funciona no mesmo servidor. **Resolvido na v0.6 (09/11/2026):** arquivos no bucket privado do Supabase Storage; `/static` removido. | `file_service.py`, `chamados.py` |
| PR-04 | Crítica | Backend | `POST /concluir` permite ao técnico marcar a OS como concluída sem passar pelas validações de odômetro, comprovantes e assinatura. | `concluir_chamado` |
| PR-05 | Crítica | Backend | Um técnico desativado mantém acesso com o token já emitido até ele expirar. A validação do token não consulta o banco. | `get_current_user`, comentário TODO |
| PR-06 | Alta | Mobile | O app chama `GET /api/auth/me`, que não existe no backend. | `frontend/src/api/tecnico.ts` |
| PR-07 | Alta | Painel | O painel envia status em formatos que o backend não aceita (`AGENDADO`, `EM_ATENDIMENTO`, `CANCELADO`, `CONCLUIDO`). O enum do backend usa "Agendado", "Em Atendimento", "Finalizado" e não tem "Cancelado". Atribuir técnico pode falhar com erro 422. | `atribuirTecnico`, `retomarVisita`, `cancelarChamado` |
| PR-08 | Alta | Painel | O painel chama pausar e concluir como administrador. Essas rotas exigem papel de técnico, então a chamada resulta em 403. A ação "retomar" chama um fluxo que não existe no backend. | `pausarVisita`, `concluirChamado`, `retomarVisita`; `require_technician_role` no backend |
| PR-09 | Alta | Painel | Não existe tela para reagendar. O método existe no serviço, mas nenhuma tela o chama. | `reagendarChamado` sem uso em views |
| PR-10 | Alta | Backend | A finalização do atendimento (assinatura) grava `nome_cliente` e `documento_cliente` na visita, campos que não existem no modelo. A operação deve falhar. **[Verificar em teste]** | `finalizar_atendimento`, `salvar_dados_cliente` |
| PR-11 | Alta | Backend | O schema de resposta da visita exige horários e `km_total > 0`. Visitas criadas em etapas, com esses campos vazios, podem causar erro de validação ao listar OS. O próprio front já mapeia uma mensagem para esse erro. **[Hipótese forte, verificar]** | `schemas/visita.py`, mensagem em `listarChamados` |
| PR-12 | Média | Backend | O cálculo de custos lê as chaves `id` e `id_os` de dicionários que trazem `id_visita` e `id_os`. Os IDs saem zerados no retorno. | `custo_service.py` |
| PR-13 | Média | Backend | Não há controle de transição de status. Qualquer estado pode ser alterado diretamente pelo técnico (exceto Finalizado). | `update_chamado` |
| PR-14 | Média | Mobile | A URL base da API está fixa em `10.0.2.2:8000`, que só funciona no emulador Android. | `frontend/src/api/api.ts` |
| PR-15 | Média | Produto | Há três listas diferentes de motivos de pausa: no mobile (5 itens), no painel (6 itens, com nomes diferentes) e no backend (texto livre). | `PausaModal`, `types.ts` |
| PR-16 | Média | Painel | O código da OS (`OS-AAAA-NNNN`) é montado no front. Ele não existe no backend nem é persistido. | `chamadoService.listarChamados` |
| PR-17 | Média | Painel | O token JWT é guardado em `localStorage`, o que o expõe em caso de falha de XSS. | `apiClient.setToken` |
| PR-18 | Média | Backend | O CORS aceita apenas `localhost`. Não há origem de produção. | `main.py` |
| PR-19 | Média | Backend | Não há migrações (`create_all` no start). O `README` cita MySQL, mas o projeto usa PostgreSQL (`psycopg2`). O script `resetar_banco.py` apaga todas as tabelas sem nenhuma trava de ambiente. | `main.py`, `resetar_banco.py`, `requirements.txt` |
| PR-20 | Média | Backend | Não há registro de auditoria (quem fez o quê). Há `print` de depuração em endpoints de deslocamento e de estado. | `finalizar_deslocamento`, `estado_visita` |
| PR-21 | Média | Backend | A mensagem "Usuário inativo" é diferente de "Email ou senha incorretos". Isso permite descobrir quais e-mails existem e estão desativados. | `auth.py` |
| PR-22 | Média | Backend | Custos de referência ficam fixos em `config.py`. Há um TODO para tela de configuração. | `config.py` |
| PR-23 | Baixa | Backend | O login percorre todos os técnicos a cada tentativa. Deve buscar apenas pelo e-mail. | `auth.py` |
| PR-24 | Baixa | Painel | Chamadas em cascata de "tentar PATCH, depois PUT" e "com e sem barra final" indicam contrato de API instável. Essas tentativas devem ser removidas depois que o contrato estiver fixado. | `apiClient.request`, `updateTecnico` |
| PR-25 | Baixa | Painel | Ao criar uma OS com equipamento, o front cria uma visita com defeito fixo "Refrigeração" e número de série gerado (`SN-<timestamp>`) quando o usuário não informa. **v0.5: obsoleto pela regra de equipamento da OS** — o painel passa a enviar apenas equipamentos reais (modelo do catálogo + número de série informado), nunca cria visita, defeito nem série gerada, e bloqueia o envio sem série. Fecha quando o painel adotar o contrato da SDD 6.13. | `criarOrdemServico` |
| PR-26 | Baixa | Repositório | Há arquivos sem uso ou legados: `frontend/package.json.mSLBw...` (cópia solta) e `in_memory_repository.py` (implementação antiga, ainda importada por causa de `deep_update`). | Árvore do repositório |

### 9.1 Atualização da v0.2

**Novos problemas, encontrados ao cruzar o código com as decisões:**

| ID | Severidade | Área | Problema | Evidência |
|---|---|---|---|---|
| PR-27 | Alta | Backend | O `codigo` do cliente é opcional no schema, mas obrigatório no banco. Criar cliente sem código resulta em erro 500. | `schemas/cliente.py`, `models/cliente.py` |
| PR-28 | Alta | Painel e backend | O cancelamento concatena o motivo na descrição do cliente e envia o status `CANCELADO`, que não existe. Não há campo próprio para motivo, data e autor. | `cancelarChamado`, `models/chamado.py` |
| PR-29 | Alta | Backend | A validação de resolução 960×1280 é aplicada a toda foto de serviço. A regra vale só para conserto. | `upload_foto_servico` |
| PR-30 | Alta | Backend e app | Os horários são gravados com a hora do servidor, em HH:mm, sem data e sem fuso. Isso é incompatível com registro offline. | `datetime.now().strftime("%H:%M")` nos endpoints |
| PR-31 | Média | Backend | Desativar técnico só muda `is_active`. As OS continuam atribuídas a ele. | `delete_tecnico` |
| PR-32 | Média | Backend | A pausa só aceita técnico e guarda apenas `por_tecnico_id`. O motivo é texto livre sem validação. | `pausar_visita`, `models/pausa.py` |
| PR-33 | Média | Backend | Os valores de custo são centralizados no sistema; não devem ser individualizados nem editáveis pelo técnico. A configuração global deve ser documentada e usada no snapshot de cada OS finalizada. | `config.py` |
| PR-34 | Baixa | Backend | Não há validação de CPF, nem do cliente na assinatura nem do técnico no cadastro. | `schemas/tecnico.py` |
| PR-35 | Alta | Backend | A assinatura é gravada na OS (`assinatura_cliente_url`). Com várias visitas, cada assinatura sobrescreve a anterior. | `finalizar_atendimento` |
| PR-36 | Média | Backend | Iniciar atendimento não exige o fim do deslocamento de ida. Só a tela impede. | `iniciar_atendimento_visita` |

**Problemas existentes que mudaram de ação:**

| ID | O que mudou |
|---|---|
| PR-03 | Confirmado: as fotos estão atualmente no disco do servidor. Migrar para bucket privado do Supabase Storage; o plano Free inclui cota de armazenamento e suporta bucket privado, com limites de uso e ressalva de pausa por inatividade. **Concluído em 09/11/2026** (17 arquivos migrados e conferidos por SHA-256). |
| PR-04 | Decisão tomada: a conclusão é automática. A ação é **remover** `POST /concluir`, e não restringi-lo. |
| PR-08 | O administrador **passa a poder pausar**. Liberar a rota ao papel `admin`. A ação "retomar" continua sem existir no fluxo. |
| PR-10 | Gravar nome, **CPF** e assinatura na **visita**, com validação de CPF. |
| PR-15 | Lista oficial definida (RN-29). Falta aplicá-la nos três projetos. |
| PR-22 | Valores permanecem **centralizados na configuração global do sistema**, sem edição pelo técnico. |

### 9.2 Atualização da v0.4 — situação no código (07/11/2026)

Situação informada na revisão documental da v0.4. **Todo item abaixo está implementado no backend e coberto apenas por testes automatizados em SQLite temporário; nenhum foi verificado contra PostgreSQL/Supabase** (ver SDD 8). "Pendente" indica que o PRD/SDD define o comportamento, mas o código ainda não o entrega.

| ID | Situação |
|---|---|
| PR-04 | Implementado: `POST /concluir` e `DELETE /chamados/{id}` removidos |
| PR-05 | Implementado: usuário ativo é consultado no banco a cada requisição |
| PR-06 | Implementado: `GET /api/auth/me` existe |
| PR-10, PR-35 | Implementado: nome, CPF e assinatura gravados na visita; `finalizar-dados` responde 410 |
| PR-18 | Implementado: `CORS_ORIGINS` por variável de ambiente |
| PR-19 | Parcial: trava de ambiente em `resetar_banco.py` e `AUTO_CREATE_TABLES`; **Alembic continua pendente** |
| PR-21, PR-23 | Implementado: mensagem única de login e busca somente por e-mail |
| PR-27, PR-29 | Implementado: `codigo` obrigatório no schema; resolução mínima só para conserto |
| PR-31 | Implementado: desativar técnico desatribui as OS (RN-08a) |
| PR-36 | Implementado: iniciar atendimento exige a ida finalizada |
| PR-01, PR-02, PR-07, PR-08, PR-09, PR-14, PR-15, PR-16, PR-17, PR-20 (parte), PR-24 a PR-26 | Não reavaliados nesta revisão documental |

### 9.3 Atualização da v0.5 — divergências da regra de equipamento (08/11/2026)

Divergências entre a regra de 08/11/2026 e o código/documentação anteriores. **Situação em 08/11/2026 (fim do dia):** PR-37 (modelos e migração `0007` **aplicada no Supabase real em 08/11/2026**; sem dados legados a migrar), PR-38 (backend e painel web implementados; painel não executado), PR-39, PR-40, PR-42 e PR-43 (backend implementado, testes em SQLite), PR-41 (app ajustado, não executado), PR-44 (sincronização: backend implementado e testado em SQLite; tabela `sync_arquivo` (migração `0009`) **aplicada no Supabase real**; app com outbox implementado e não executado). PR-45 está decidido.

| ID | Severidade | Área | Problema |
|---|---|---|---|
| PR-37 | Alta | Banco e backend | Número de série e nome do equipamento são texto livre digitado pelo técnico em `servico_equipamento`. Passam a vir do vínculo da OS; é necessária migração de dados legados (SDD 4.9). |
| PR-38 | Alta | Backend e painel | `ChamadoCreate` não tem equipamentos; não existem catálogo, tela de modelos nem vínculo na OS. |
| PR-39 | Alta | Backend e app | Os schemas de serviço aceitam `numero_serie_atendido` e `nome_equipamento`, e o app (`registroEquipamento.tsx`, `api/servico.ts`) os envia. Devem ser removidos da entrada; os testes e helpers atuais que os enviam quebram. |
| PR-40 | Alta | Backend | `iniciar_atendimento` não valida foto de defeito, `finalizar_atendimento` não valida conserto salvo nem foto de conserto, e o `GET .../estado` não informa pendências. Há dois caminhos de início (rota da OS e rota da visita): a checagem deve ficar no serviço. |
| PR-41 | Alta | App | A foto de defeito hoje só existe depois de iniciar o atendimento e é opcional; a regra a exige antes do início. O fluxo e a ordem das telas mudam (SDD 6.6 e 6.7). |
| PR-42 | Média | Backend | O upload de foto de serviço não depende da fase do atendimento (conserto antes de iniciar, upload após finalizar). Regras de fase em SDD 6.7. |
| PR-43 | Média | Backend | Salvar e atualizar serviço não geram registro em `log_acao`. |
| PR-44 | Média | Sincronização | O contrato offline (`servico_salvo`, `foto_servico`, cache de OS) usa série digitada pelo técnico e não conhece equipamentos nem as novas pré-condições (SDD 6.12). A sincronização continua não implementada. |
| PR-45 | Baixa | Produto | Renomear modelo reescreve o histórico exibido (sem cópia do nome). **Decidido pelo responsável em 08/11/2026: é o comportamento desejado**; a renomeação é auditada. Registrado só para não ser tratado como defeito. |

## 10. Premissas

- O backend é a única fonte de verdade. Painel e app não devem guardar regra de negócio.
- O Supabase é usado como PostgreSQL gerenciado, acessado pela string `DATABASE_URL`. Os arquivos estão atualmente no disco do servidor e devem migrar para Supabase Storage em bucket privado.
- O Supabase Storage oferece bucket privado no plano Free; a cota atual documentada é 1 GB de armazenamento de arquivos e 5 GB de egress. Projetos Free podem ser pausados após uma semana de inatividade. A operação deve monitorar cotas e decidir o upgrade para Pro conforme disponibilidade/continuidade e volume exigidos.
- O técnico pode operar offline por até 24 horas desde a última autenticação online bem-sucedida. Não existe refresh token. A fila não pode ser apagada se a sessão expirar.
- Imagens aceitas são JPEG/PNG, com limite de 15 MB por arquivo e resolução mínima equivalente a 960 × 1280 (menor lado ≥ 960 e maior lado ≥ 1280, em qualquer orientação) somente para foto de conserto.
- Valores de referência de custo são globais, mantidos na configuração do sistema; não são editáveis por técnico e o cálculo é congelado ao finalizar a OS.
- Ajudantes não fazem parte do escopo desta etapa.
- Notificações push, e-mail e WhatsApp não fazem parte do escopo desta versão.
- Cada cliente tem poucas OS por dia. Não há necessidade de agenda com conflito de horário nesta versão.
- **Risco aceito (PO, 07/11/2026): ambiente compartilhado.** Nesta fase, desenvolvimento e produção usam o **mesmo projeto Supabase**, por decisão do PO. Isso significa que testes, scripts e migrações de desenvolvimento podem atingir dados reais. **Ressalva de Segurança (SEG):** a separação de ambientes é controle recomendado (SEG-05, SEG-12, SEG-14); o risco é aceito pelo PO e deve ser reavaliado antes do uso em produção plena.

## 11. Decisões complementares e pendências

### 11.1 Decisões confirmadas pelo responsável em 29/10/2026

| Tema | Decisão consolidada |
|---|---|
| Reagendamento em `Pausado` | Não permitir. O técnico precisa finalizar o deslocamento de volta; a OS passa a `Aguardando Reagendamento`; só então o admin agenda a próxima visita. |
| Reagendamento em `Agendado` sem ida iniciada | Alterar a data da visita existente, sem criar visita vazia. |
| Valores de custo | Configuração global do sistema, não individual por técnico; técnico não pode alterar. |
| Conflito de sincronização offline | Em conflito com alteração administrativa incompatível, a OS não finalizada passa para `Pendente`, sem técnico, para análise/reatribuição. Ações/arquivos devem manter rastreabilidade; nenhum dado pode ser descartado silenciosamente. |
| Pausa pelo admin | Permitida quando a visita estiver em atendimento e não finalizada; registrar autor e papel. |
| Cancelamento | Exige motivo; permitido em qualquer status exceto Finalizado ou já cancelado; nesses casos retornar conflito. |
| Status `Pendente` | OS criada, não finalizada e sem técnico atribuído. `Aberto` fica obsoleto. |
| Custo | Congelar cálculo e valores usados na finalização. |
| Ajudantes | Fora do escopo nesta etapa. |
| Arquivos | Atualmente em disco de servidor; migrar para bucket privado do Supabase Storage, inicialmente usando as cotas gratuitas se suficientes. |
| Sessão offline | Até 24 horas desde autenticação online; não implementar refresh token. Preservar outbox após expiração. |
| Limite de imagem | 15 MB por arquivo de imagem, JPEG/PNG. |
| Quilometragem | `km_total = (km_fim_ida − km_inicio_ida) + (km_fim_volta − km_inicio_volta)`. |
| Desempenho | Metas quantitativas definidas em RNF-05. |
| Notificações | Não necessárias; fora do escopo. |
| Indicadores | Metas quantitativas definidas na seção 3. |
| Problema de negócio | Confirmado: registros manuais e falta de rastreabilidade/centralização motivaram o sistema. |

### 11.1.1 Decisões do PO em 07/11/2026

| Tema | Decisão consolidada |
|---|---|
| RN-08a — Desativação de técnico | **Resolvida.** Desatribuir automaticamente todas as OS não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) → `Pendente`, sem técnico; histórico (visitas, fotos, serviços, pausas) preservado; Finalizadas/canceladas não mudam; auditoria em `log_acao`. Na reatribuição, visita iniciada pelo técnico anterior vira histórico e é criada visita nova. |
| Visita automática | Toda OS que entra em `Agendado` ganha uma visita aberta na mesma transação; `data_visita` = `data_agendamento` ou hoje (America/Sao_Paulo). Segunda visita enquanto houver uma não finalizada é recusada (409). |
| CPF/CNPJ | CPF e CNPJ do técnico com máscara canônica (14 e 18 caracteres); CPF do cliente na visita só com dígitos (11). |
| Administrador e OS | O administrador não pode receber OS; só o papel `tecnico` é atribuível. |
| Custo de visita pausada | O tempo de serviço de visita pausada conta zero no custo (atendimento não finalizado). |
| Foto de conserto | Mínimo equivalente a 960 × 1280 em qualquer orientação (menor lado ≥ 960 e maior lado ≥ 1280). |
| Ambiente | Dev e produção compartilham o mesmo projeto Supabase nesta fase (risco aceito; ressalva de SEG na seção 10). |

### 11.1.2 Decisão do responsável em 08/11/2026 — equipamento da OS

| Tema | Decisão consolidada |
|---|---|
| Quem cadastra o equipamento | O técnico **não** cadastra equipamento; o equipamento a consertar já vem na OS. |
| Catálogo | O painel admin tem um cadastro de Equipamento contendo **somente o modelo** (ex.: Freezer vertical modelo X, Freezer vertical modelo Y, Freezer horizontal modelo X). |
| Vínculo | Ao criar a OS o administrador vincula o modelo e o **número de série**; pode vincular **mais de um equipamento** na mesma OS. |
| Edição pelo técnico | O técnico não edita o equipamento da OS, nem o número de série. |
| Iniciar atendimento | Não pode ser iniciado sem a **foto do defeito** registrada. |
| Finalizar atendimento | Não pode ser finalizado sem o **conserto da OS salvo** e a **foto do conserto**. |

**Confirmações do responsável (segunda rodada, 08/11/2026) sobre o detalhamento**

| # | Tema | Decisão confirmada |
|---|---|---|
| Q-EQ1 | Granularidade das exigências de foto | A exigência vale **por equipamento da OS** (foto de defeito para iniciar; conserto salvo + foto de conserto para finalizar). Como fotos e serviços pertencem à visita (RN-15), é verificada a cada visita. |
| Q-EQ2 | O que é "salvar o conserto" | Interpretação aprovada: marca explícita "Conserto salvo" por equipamento, com ao menos um defeito principal; materiais opcionais (RN-47). |
| Q-EQ3 | Edição pelo administrador | Só **até o início do atendimento**; do início até a finalização não há edição; **volta somente quando a OS estiver Finalizada**, para corrigir fotos comprobatórias e materiais utilizados (RN-45, RN-49). |
| Q-EQ4 | OS sem equipamento | **Toda OS precisa ter ao menos um equipamento vinculado; OS sem equipamento não devem ser criadas** (RN-41). OS legadas sem equipamento ficam bloqueadas até o vínculo (RN-46). |
| Q-EQ5 | Renomear modelo | **Reescreve o histórico exibido**, com auditoria (PR-45). |

### 11.2 Pendências

**Regra de equipamento (v0.5): sem pontos em aberto.** As duas últimas dúvidas foram respondidas pelo responsável em 08/11/2026:

| # | Pergunta | Decisão do responsável |
|---|---|---|
| Q-EQ6 | A correção administrativa de **materiais** em OS Finalizada deve recalcular o custo? | **Sim, recalcula.** O custo é recalculado com os materiais corrigidos, mantendo os valores de referência congelados na finalização; o snapshot é substituído e o total anterior/novo vai para `log_acao` (RN-49). |
| Q-EQ7 | Em OS Finalizada, além de fotos e materiais, o admin pode corrigir modelo e número de série? | **Não.** Somente fotos e materiais são passíveis de edição após a finalização; modelo e número de série permanecem travados (RN-45, RN-49). |

Não há outra decisão de negócio bloqueante em aberto: a RN-08a foi resolvida em 07/11/2026. Permanecem como **pendências técnicas registradas** (detalhes e status na SDD 8, 9 e 12):

- Equipamentos da OS (v0.5) e sincronização offline: backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 414 testes automatizados em SQLite (v0.6, 09/11/2026) e um smoke ponta a ponta da v0.5 (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), seguidas das migrações `0010` a `0013` da v0.6. Entre 09 e 11/11/2026 o backend foi executado contra esse PostgreSQL, o painel web foi aberto no navegador e o app do técnico foi usado contra o backend nas verificações manuais de segurança registradas na SDD v0.6.1 (RLS, TLS `verify-full`, storage privado, JWT adulterado, hash de upload, selo da visita e cifra adulterada); a suíte de regras de negócio ainda não foi repetida contra o PostgreSQL (SDD 4.8, 4.9, 6.6, 6.7, 6.12, 6.13).

- Storage privado (SEG-09, PR-03): **implementado em 09/11/2026**; `/static` não serve mais arquivos e a leitura passa pelas rotas autenticadas da API (sem URLs assinadas).
- Sincronização offline (`/api/sync`), fila e sessão offline de 24 h no app (SY-xx, RN-35 a RN-39): **implementadas** (backend e app); a janela de 24 h offline ainda não foi exercitada em aparelho.
- Migrações com Alembic (PR-19) e verificação em PostgreSQL/Supabase (os testes automatizados rodam só em SQLite; verificações manuais de segurança foram feitas no Supabase real entre 09 e 11/11/2026, ver SDD v0.6.1).
- Cookie `HttpOnly` no painel (SEG-04, PR-17), limitação de tentativas de login (rate limit) e auditoria de login e de CRUD (PR-20).
- CPF mascarado no painel é apenas visual (M3); a regra de armazenamento está em RN-06.
- Vulnerabilidades transitivas de dependências do Expo no app.

### 11.3 Interpretações técnicas aplicadas

- A resposta sobre conflito offline foi operacionalizada como transição para `Pendente` com remoção da atribuição do técnico, pois `Pendente` foi definido como OS não finalizada sem técnico. A API deve registrar o conflito e preservar os eventos/arquivos, inclusive quando rejeitados. Cancelamento e finalização não são revertidos por esse mecanismo.
- A decisão de usar Supabase Storage privado não significa que o armazenamento é ilimitado ou que o serviço nunca gera custo. Usar o Free dentro das cotas; plano Pro ou outra arquitetura pode ser necessário quando a continuidade e o volume de produção exigirem.

- As duas travas da v0.5 (RN-43 e RN-44) respondem **HTTP 409** (conflito com o estado da visita, resolvível pelo técnico ao registrar a foto ou salvar o conserto), com a lista de pendências no `detail`. A alternativa seria 400, por coerência com RN-17; o código é decisão técnica reversível, registrada na SDD 6.1.
- A regra de 08/11/2026 não altera a lista de defeitos e sub-defeitos existente; "conserto" é interpretado como o registro de defeitos e materiais do equipamento com a marca "Conserto salvo" (RN-47).

## 12. Critérios de aceite de alto nível

- **CA-01** Dado um técnico atribuído, quando ele completa o fluxo normal, então a OS termina em `Finalizado`, com assinatura registrada e custo calculado/congelado.
- **CA-02** Dado um atendimento em andamento, quando o técnico pausa e completa o deslocamento de volta, então a OS termina em `Aguardando Reagendamento`, e a interface não mostra ação de concluir OS manualmente.
- **CA-03** Dada uma OS em `Aguardando Reagendamento`, quando o administrador agenda nova data, então uma nova visita é criada, a OS fica `Agendado` e a pausa anterior é encerrada.
- **CA-04** Dado um técnico logado, quando ele tenta acessar uma OS de outro técnico, então recebe erro de acesso negado.
- **CA-05** Dado um administrador no painel, quando a API falha, então o painel mostra erro claro e não exibe dados fictícios.
- **CA-06** Dada uma visita com pedágio maior que zero, quando o técnico tenta finalizar sem comprovante, então recebe erro de comprovante obrigatório.
- **CA-07** Dada uma visita em atendimento, quando o administrador pausa com motivo `Outro` sem descrição, então recebe erro; com descrição, a pausa é criada e registrada com papel `admin`.
- **CA-08** Dada uma OS não finalizada, quando o administrador cancela sem motivo, então recebe erro; com motivo, a OS recebe flag e metadados de cancelamento. OS Finalizada ou já cancelada retorna conflito.
- **CA-09** Dado um técnico sem internet por até 24 horas desde o último login online, quando executa o fluxo e depois reconecta/autentica, então as ações aplicadas aparecem no banco com os horários de ocorrência e sem duplicidade; nenhuma ação/arquivo pendente é apagada.
- **CA-10** Dado um CPF inválido do cliente, quando o técnico finaliza o atendimento, então a ação é recusada com mensagem de CPF inválido.
- **CA-11** Dada uma OS `Pausado`, quando o administrador tenta reagendar antes do técnico terminar a volta, então recebe HTTP 409; após a volta, a OS passa para `Aguardando Reagendamento` e pode ser reagendada.
- **CA-12** Dado um técnico desativado, então o token existente deixa de funcionar na requisição seguinte e todas as suas OS não finalizadas e não canceladas (Agendado, Em Atendimento, Pausado, Aguardando Reagendamento) passam a `Pendente`, sem técnico, com visitas, fotos, serviços e pausas preservados e a ação auditada em `log_acao`; OS Finalizadas e canceladas permanecem inalteradas (RN-08a).
- **CA-13** Dada uma OS com duas visitas, então cada visita tem sua própria assinatura, e a segunda não sobrescreve a primeira.
- **CA-14** Dada uma foto de defeito abaixo de 960 × 1280, então ela é aceita. Foto de conserto é aceita se o menor lado for ≥ 960 e o maior lado ≥ 1280, em qualquer orientação (1280 × 960 e 960 × 1280 aceitas); abaixo disso é recusada.
- **CA-15** Toda imagem maior que 15 MB é recusada pelo app e pela API; arquivos até 15 MB são aceitos se cumprirem os demais critérios.
- **CA-16** Dada uma OS criada sem técnico, então seu status é `Pendente`; ao atribuir técnico ativo, passa para `Agendado`.
- **CA-17** Dado conflito de sincronização por ação administrativa incompatível, então a OS não finalizada passa para `Pendente`, fica sem técnico, o conflito é auditado e os registros locais são apresentados como rejeitados/pendentes de tratativa, nunca apagados silenciosamente.
- **CA-18** O app permite o uso offline até 24 horas desde a última autenticação online, não usa refresh token e preserva a fila após expiração/limite.
- **CA-19** Os valores de custo são globais; nenhum técnico consegue consultar ou alterar uma configuração individual. O custo finalizado permanece inalterado após mudança futura da configuração global.
- **CA-20** Em homologação, listagens/detalhes atendem p95 ≤ 2 s na carga definida em RNF-05 e upload de imagem de 15 MB atende ≤ 30 s no perfil de rede definido.
- **CA-21** Dada uma OS que entra em `Agendado` (criação com técnico, atribuição ou reagendamento), então existe uma visita aberta criada na mesma transação, com `data_visita` = `data_agendamento` ou, se vazia, a data de hoje em America/Sao_Paulo; tentar criar outra visita enquanto houver uma não finalizada retorna 409.
- **CA-22** Dado um usuário com papel `admin`, quando se tenta atribuir uma OS a ele (na criação ou na edição), então a operação é recusada.
- **CA-23** Dada uma OS reatribuída após a desativação do técnico anterior, então a visita iniciada pelo técnico anterior permanece como histórico e existe uma visita nova para o novo técnico.
- **CA-24** Dada uma visita pausada, então seu tempo de serviço contribui com zero para o custo da OS.
- **CA-25** Dado o administrador mantendo o catálogo, quando cadastra um modelo com nome repetido (ignorando maiúsculas e espaços nas pontas), então recebe conflito; o técnico não consegue criar, editar nem desativar modelo.
- **CA-26** Dado o administrador criando uma OS, quando envia sem nenhum equipamento, então a API recusa (422) e nada é criado; com um ou mais equipamentos (modelo ativo + número de série), a OS é criada com todos os vínculos, inclusive vários do mesmo modelo.
- **CA-27** Dada uma OS com o número de série "AB-1", quando o administrador vincula outro equipamento com "ab-1" na mesma OS, então é recusado (conflito); o mesmo número em outra OS é aceito.
- **CA-28** Dado o técnico, quando tenta criar, editar ou remover equipamento, modelo ou número de série (ou envia esses campos ao registrar o serviço), então a API recusa e o app não exibe campo editável para eles.
- **CA-29** Dada uma OS com 2 equipamentos e foto de defeito em apenas 1, quando o técnico tenta iniciar o atendimento, então recebe 409 listando o equipamento pendente; com foto nos dois, o atendimento inicia e a OS vai para `Em Atendimento`.
- **CA-30** Dado um atendimento iniciado com conserto salvo e foto de conserto (≥ 960 × 1280 em qualquer orientação) em apenas 1 de 2 equipamentos, quando o técnico tenta finalizar, então recebe 409 listando o pendente e nenhuma assinatura é gravada; com tudo completo, a finalização é aceita.
- **CA-31** Dado o registro de serviço criado apenas para receber a foto do defeito (sem "Salvar conserto"), quando o técnico tenta finalizar o atendimento, então é recusado (conserto não salvo).
- **CA-32** Dada uma visita pausada, quando o técnico finaliza o deslocamento de volta, então a OS vai para `Aguardando Reagendamento` sem exigir conserto salvo nem foto de conserto.
- **CA-33** Dada a segunda visita de uma OS (após reagendamento), quando o técnico tenta iniciar o atendimento sem foto de defeito nessa visita, então é bloqueado, mesmo que a primeira visita tenha as fotos.
- **CA-34** Dado que o atendimento da visita vigente foi iniciado, quando o administrador tenta alterar o número de série ou o modelo de um equipamento, então recebe 409 (inclusive com a OS já Finalizada, em que só fotos e materiais são corrigíveis, CA-37); antes do início a alteração é aceita e auditada em `log_acao`. Equipamento com registro de foto, defeito, material ou conserto não pode ser removido.
- **CA-35** Dada uma OS legada sem equipamento, quando se tenta atribuí-la, reagendá-la ou iniciar o atendimento, então é recusado (409) até o administrador vincular ao menos um equipamento. Dada a criação de uma OS nova sem equipamento, então é recusada (422) — ver CA-26.
- **CA-36** Dado o técnico offline, quando o evento de início do atendimento chega sem foto de defeito aplicada (ou o de finalização sem conserto/foto), então o evento é rejeitado com motivo rastreável, nenhum evento ou arquivo é apagado e a fila não trava (RN-37a).
- **CA-37** Dada uma OS **Finalizada**, quando o administrador substitui uma foto comprobatória ou corrige os materiais de um equipamento, então a correção é aceita e auditada em `log_acao` (antes/depois); ao corrigir materiais o **custo da OS é recalculado** com os valores de referência congelados na finalização (o snapshot é substituído e o total anterior/novo é auditado) e a OS continua `Finalizado`; remover a última foto de defeito ou de conserto de um equipamento é recusado (409); alterar modelo ou número de série é recusado (409); o técnico recebe 403/409 em qualquer dessas correções. Em OS que não esteja Finalizada (ou que esteja cancelada) a correção do administrador é recusada (409).

## 13. Histórico de versões

| Versão | Data | Alterações |
|---|---|---|
| 0.2 | 29/10/2026 | Decisões iniciais do negócio, PRD e diagnóstico de divergências. |
| 0.3 | 29/10/2026 | Reagendamento após retorno, status Pendente para OS sem técnico, custos globais congelados, conflito offline, sessão de 24 h sem refresh token, limite de imagem de 15 MB, armazenamento privado, metas e exclusão de ajudantes/notificações do escopo. |
| 0.5 (atualização de situação) | 12/11/2026 | **Sem mudança de regra de negócio; numeração mantida em 0.5.** Nota de situação sobre a ampliação da cifragem de dados pessoais em repouso (contato principal do cliente, nome do signatário e nome/CPF no histórico de sincronização), implementada e testada só em SQLite, com a migração `0014` ainda não aplicada e nada verificado em PostgreSQL/Supabase; texto de RNF-02 detalhando o que é cifrado, o que fica em claro e os limites. Detalhes técnicos na SDD v0.7. |
| 0.5 | 08/11/2026 | Regra de equipamento da OS: o técnico não cadastra equipamento; catálogo de modelos e vínculo modelo + número de série na OS pelo administrador, com vários equipamentos por OS (nova seção 6.10; RF-23 a RF-25; RN-40 a RN-48); técnico não edita equipamento nem série; atendimento só inicia com a foto do defeito (RN-43) e só finaliza com o conserto salvo e a foto do conserto (RN-44, RN-47), por equipamento e por visita; pausa dispensa essas exigências (RN-48); fluxo da visita reordenado (6.5); RF-09, RF-17, RN-16, RN-17, RN-22 e PR-25 ajustados; O2 revista; escopo atualizado; nova seção 9.3 (PR-37 a PR-45); decisões do responsável (08/11/2026) e pontos em aberto em 11.1.2 e 11.2; CA-25 a CA-37 criados. Confirmado pelo responsável em 08/11/2026: exigência por equipamento da OS; "conserto salvo" como marca explícita (RN-47); edição pelo admin só até o início do atendimento e de volta apenas com a OS Finalizada, para corrigir fotos e materiais (RN-45, RN-49); OS sempre com ao menos um equipamento (RN-41, RN-46); renomear modelo reescreve o histórico (PR-45). A correção de materiais pós-finalização **recalcula o custo** (valores congelados reutilizados) e só fotos e materiais são editáveis após a finalização. Implementação em 08/11/2026: backend implementado (equipamentos, correção pós-finalização com recálculo de custo e sincronização offline `/api/sync/*`) com 414 testes automatizados em SQLite (v0.6, 09/11/2026) e um smoke ponta a ponta da v0.5 (378 passos) contra SQLite temporário; migrações `0007` e `0009` **aplicadas no Supabase real (projeto `bsuehcxvnfawmabielhl`) em 08/11/2026 pelo MCP, em 5 partes** (objetos, constraints, RLS e dados existentes conferidos por consulta; `get_advisors` sem WARN/ERROR), seguidas das migrações `0010` a `0013` da v0.6. Entre 09 e 11/11/2026 o backend foi executado contra esse PostgreSQL, o painel web foi aberto no navegador e o app do técnico foi usado contra o backend nas verificações manuais de segurança registradas na SDD v0.6.1 (RLS, TLS `verify-full`, storage privado, JWT adulterado, hash de upload, selo da visita e cifra adulterada); a suíte de regras de negócio ainda não foi repetida contra o PostgreSQL. |
| 0.4 | 07/11/2026 | RN-08a resolvida (desatribuição automática na desativação do técnico); visita automática ao entrar em Agendado (RN-11a); máscara canônica de CPF/CNPJ do técnico (RN-06); administrador não recebe OS (RN-08); técnico não altera status por edição (RN-13); tempo de serviço de visita pausada vale zero no custo (RN-31); foto de conserto 960 × 1280 em qualquer orientação (RN-21); ambiente compartilhado dev/produção como risco aceito (seção 10); nova seção 9.2 com a situação dos PR no código; CA-12 e CA-14 atualizados e CA-21 a CA-24 criados. |
