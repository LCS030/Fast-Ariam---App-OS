# Migracoes SQL - Fast Ariam (alinhamento ao SDD v0.3, secao 4.7)

Scripts SQL versionados e idempotentes. **Alembic nao esta configurado** (pendencia PR-19): estes arquivos foram
escritos para virar revisoes Alembic depois (cada arquivo = uma revisao; `DO $mig$` -> `op.execute`).
**Nenhum script foi aplicado a nenhum banco** pelo agente DBA nesta rodada (acesso remoto somente leitura) e **nenhum foi
executado em PostgreSQL** (nao havia instancia local); revise e teste num branch/copia antes do remoto.

## Pre-requisitos
- Backup/snapshot do banco (o remoto tem dados reais: 2 OS, 2 visitas, 1 pausa ativa).
- PostgreSQL 15+ (remoto: 17.11). Executar com o dono das tabelas (`postgres`):
  `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f <arquivo>`.
- Rodar `0000_inventario.sql` (somente leitura) antes e depois.
- Enum `statuschamado`: **nenhum valor novo e necessario** (os 6 status de negocio ja existem; `Aberto` fica como
  valor legado - Postgres nao remove valores de enum). Se um dia for preciso, `ALTER TYPE ... ADD VALUE` nao pode
  rodar dentro de transacao com uso do valor novo: execute-o em script proprio, fora de `BEGIN/COMMIT`, e use o valor
  somente num script/transacao posterior.

## Ordem de execucao

| # | Arquivo | Tipo | Quando |
|---|---|---|---|
| 0 | `0000_inventario.sql` | leitura | sempre, antes/depois |
| 1 | `0001_alinhar_sdd_v03.sql` (+ `0001_rollback.sql`) | EXPANDIR (aditivo, backfill seguro) | primeiro; compativel com o backend atual |
| - | deploy do Backend novo | | usa `por_usuario_id`/`por_papel`, colunas novas, `Pendente` sem tecnico |
| 3 | `0003_legado_manual.sql` | assistido (tudo comentado) | se o inventario mostrar `Aberto/Pendente` com tecnico, canceladas sem motivo etc. |
| 2 | `0002_constraints_estado.sql` (+ `0002_rollback.sql`) | ENDURECER | so depois do backend novo e do legado resolvido |
| 5 | `0005_rls_opcional.sql` (+ `0005_rollback.sql`) | opcional (SEG-12) | apos confirmar que o usuario do `DATABASE_URL` e dono/BYPASSRLS | **RLS LIGADO no Supabase real, conferido em 11/11/2026** (`relrowsecurity = true` nas 17 tabelas de `public`, `pg_policies` vazio). Nao ha registro aqui de quando/por qual script foi ligado (0005 ou parte3 da 0007). |
| 6 | `0006_indices_fk_opcional.sql` | opcional | quando houver volume e plano de execucao que justifique |
| 4 | `0004_contracao_opcional.sql` (+ `0004_rollback.sql`) | CONTRAIR (destrutivo) | por ultimo, depois de o Backend nao usar mais `por_tecnico_id`/`is_completed` |
| 7 | `0007_equipamento_os.sql` (+ `0007_rollback.sql`) | EXPANDIR + BACKFILL (SDD v0.5, 4.8/4.9) | backup + ensaio em dump local antes; compativel com o backend antigo; depois, deploy do Backend v0.5 (dois modos) | **APLICADA no Supabase real em 08/11/2026 (MCP).**
| 8 | `0008_contracao_equipamento_opcional.sql` (**nao escrita**; so descrita abaixo) | CONTRAIR | apos aceite do PO e backend v0.5 estavel em producao |
| 9 | `0009_sync_arquivo.sql` (+ `0009_rollback.sql`) | ADITIVA (SDD v0.5, 6.12) | cria `sync_arquivo` (arquivos da sincronizacao offline); independe da 0007; ensaiar em dump antes (dev = producao) | **APLICADA no Supabase real em 08/11/2026 (MCP).**
| 10 | `0010_integridade.sql` (+ `0010_rollback.sql`) | ADITIVA (v0.6) | colunas `sha256` (sync_arquivo, servico_foto, comprovante) e `assinatura_sha256`, `arquivos_sha256`, `selo_integridade`, `selo_versao` em `visita`; backup antes (`scripts/backup_banco.py`) | **APLICADA no Supabase real em 08/11/2026 (MCP).** |
| 11 | `0011_cifragem.sql` (+ `0011_rollback.sql`) | INVASIVA (v0.6) | colunas sensiveis do tecnico e `visita.documento_cliente` viram `text`; remove CHECK do CPF e UNIQUE do CNPJ; cria `tecnico.cnpj_idx` (indice cego). **Ordem: backup -> 0011 -> `scripts/cifrar_dados_existentes.py` -> 0012.** O rollback exige antes `cifrar_dados_existentes.py --decifrar` | **APLICADA no Supabase real em 08/11/2026 (MCP).** |
| 12 | `0012_cnpj_idx_obrigatorio.sql` (+ `0012_rollback.sql`) | ENDURECER (v0.6) | `tecnico.cnpj_idx NOT NULL`; so depois do script de cifragem (aborta se sobrar NULL) | **APLICADA no Supabase real em 08/11/2026 (MCP).** |
| 7+9 | `sql_editor_v05_aplicar.sql` / `sql_editor_v05_rollback.sql` | Script unico equivalente para o SQL Editor (gerado de 0007 + 0009; sintaxe validada com o parser do PostgreSQL) | **O conteudo ja foi aplicado no Supabase real em 08/11/2026 pelo MCP, em 5 partes** (`equipamento_os_v05_parte1_tabelas`, `parte2a_colunas_constraints_trigger`, `parte2b_serie_legada_anulavel`, `parte3_backfill_rls`, `sync_arquivo_v05`); nao precisa ser executado de novo (e idempotente). O rollback continua valido |

(A numeracao reflete a criacao; a ordem real de uso e a da tabela: 0 -> 1 -> deploy -> 3 -> 2 -> 5/6 -> 4; a trilha
v0.5 e independente: 7 -> deploy do Backend v0.5 -> completar OS legadas sem equipamento -> (8 opcional).)

## O que o 0001 faz
- `ordem_servico`: `motivo_cancelamento TEXT`, `cancelado_em TIMESTAMPTZ`, `cancelado_por INT -> tecnico`; defaults
  (`status='Pendente'`, `is_cancelled=false`, `em_garantia=true`); `assinatura_cliente_url` text -> varchar(255)
  (so se nenhum valor > 255); `Aberto` sem tecnico -> `Pendente`.
- `visita`: `assinatura_url`, `nome_cliente_assinatura`, `documento_cliente VARCHAR(11)` (CHECK so digitos),
  `ida_/atendimento_/volta_ inicio_em|fim_em TIMESTAMPTZ`; `km_total` DEFAULT 0 (ja era NOT NULL); defaults de
  `valor_pedagio`, `valor_frete_devolucao`, `servico_finalizado`. `hora_*` e ajudantes permanecem (legado, sem uso).
- `pausa`: `por_usuario_id -> tecnico`, `por_papel`, `encerrada_em`; backfill de autor/papel; CHECKs de motivo (5 valores),
  `Outro` exige descricao, `por_papel`, ativa sem `encerrada_em`.
- CHECKs `servico_foto.tipo` (defeito|conserto) e `comprovante.tipo` (pedagio|frete).
- Novas tabelas: `configuracao_custo` (linha unica id=1, global, nao semeada), `custo_os`, `sync_evento`, `log_acao`
  (+ indices; `REVOKE` de anon/authenticated nessas 4 tabelas).
- CHECKs sao criados `NOT VALID` e validados em seguida; se o legado violar, ficam `NOT VALID` com WARNING (valem para
  escritas novas, nao reprovam dados antigos).

## O que o 0007 faz (equipamentos por OS, SDD v0.5 secoes 4.5, 4.8, 4.9)
**Escrito, nao executado em nenhum banco nem em PostgreSQL.** Dev e producao compartilham o mesmo projeto Supabase:
a execucao real e em producao. Ensaiar antes em dump restaurado em PostgreSQL local, em janela de baixo uso, com
`psql -v ON_ERROR_STOP=1`. Fazer `pg_dump` das tabelas `ordem_servico`, `visita`, `servico_*`, `material`, `pausa` e
guardar fora do Supabase (o plano Free pode nao ter backup automatico: confirmar). Inventario: consultas SELECT
**comentadas** no topo do proprio 0007 (nada destrutivo e executado); guardar o resultado e os checksums antes/depois.
Ordem dentro do arquivo (tudo em um `BEGIN/COMMIT`, `lock_timeout` 10s, idempotente):
1. Cria `equipamento_modelo` (CHECK modelo sem espacos nas pontas e nao vazio; indice unico em `lower(modelo)`) e
   `os_equipamento` (FKs `ON DELETE RESTRICT`; CHECKs de serie e `origem` em `admin|backfill_legado`; indice unico
   `(id_os, upper(numero_serie))`; indice em `id_equipamento_modelo`).
2. `servico_equipamento`: `id_os_equipamento` (FK RESTRICT), `conserto_salvo_em TIMESTAMPTZ`,
   `is_legado BOOLEAN NOT NULL DEFAULT true` (**default true e obrigatorio na expansao**: o backend antigo continua
   inserindo servicos sem vinculo); `numero_serie_atendido` perde o NOT NULL; `ck_servico_equip_vinculo`,
   `ck_servico_equip_identificacao` e `UNIQUE (id_visita, id_os_equipamento)` (guarda `IF NOT EXISTS`); indice em
   `id_os_equipamento`.
3. Trigger `trg_servico_equip_mesma_os` (`SET search_path = public`): recusa (erro 23514) vinculo cujo `id_os` difere
   do `id_os` da visita.
4. Semeia o catalogo com `DISTINCT btrim(nome_equipamento)` (variantes que so diferem por caixa colidem em `lower()`:
   fica uma grafia; o admin mescla depois). Sem nome: modelo **`Não catalogado`** (a revisar), criado so se houver
   servico legado sem nome e com serie. **Decisao de negocio**: se o PO preferir que esses servicos fiquem
   `is_legado = true`, comentar esse INSERT (viram excecao sozinhos).
5. Backfill de `os_equipamento` (`origem = 'backfill_legado'`, `ON CONFLICT DO NOTHING`) e do vinculo
   (`id_os_equipamento`, `is_legado = false`) so onde `id_os_equipamento IS NULL`, casando serie e modelo (`lower`).
   Varias visitas da mesma OS com a mesma serie -> **um** `os_equipamento`, varios servicos.
   **Excecoes ficam `is_legado = true`** com a serie preservada: serie nula/vazia, duplicata na mesma visita (so o de
   menor `id_servico` e vinculado), mesma serie com nome diferente na mesma OS. `conserto_salvo_em` NAO e preenchido
   (proposta comentada no arquivo; decidir no inventario). Um NOTICE/WARNING resume contagens e OS em andamento sem
   equipamento.
6. Exposicao: `REVOKE ALL ... FROM anon, authenticated` nas 2 tabelas e nas sequences das identities (feito na propria
   migracao, como no 0001; ignorado se os papeis nao existirem). **RLS (sem policies) segue o padrao opcional/separado
   do 0005**: so e ligado nas 2 tabelas novas se a sessao declarar `SET fast_ariam.habilitar_rls = 'sim';` ou se o RLS
   ja estiver ligado em `ordem_servico` (0005 aplicado, usuario do `DATABASE_URL` ja validado como dono/BYPASSRLS).
   Caso contrario emite NOTICE e as tabelas ficam com RLS desligado e grants revogados ate o 0005 ser aplicado
   (a lista do `0005_rls_opcional.sql` nao inclui as tabelas novas; incluir `equipamento_modelo` e `os_equipamento`
   quando for aplicado). Depois, rodar `get_advisors` (Supabase).

**Rollback (`0007_rollback.sql`)**: reverte so a fase aditiva, com o backend antigo no ar: remove trigger/funcao e
constraints, `UPDATE ... SET id_os_equipamento = NULL, is_legado = true`, apaga `origem = 'backfill_legado'`, dropa
indice, colunas e tabelas, e restaura `NOT NULL` de `numero_serie_atendido` somente se nao houver NULL (senao WARNING).
**Aborta** se houver dados posteriores ao go-live (os_equipamento de outra origem, `conserto_salvo_em`, servicos sem
serie legada) a menos que `SET fast_ariam.confirmar_perda_dados = 'sim';`. Depois do go-live prefira *roll-forward*.

**Contracao (0008, opcional, NAO escrita)**: apos aceite do PO e backend v0.5 estavel, trocar
`ALTER TABLE public.servico_equipamento ALTER COLUMN is_legado SET DEFAULT false;`. **Nao** aplicar NOT NULL em
`id_os_equipamento` (o CHECK ja cobre) e **nunca** remover `nome_equipamento` nem `numero_serie_atendido`. Antes de
ligar o novo app, completar as OS legadas em andamento sem equipamento (RN-46/TR-15). O backend v0.5 deve gravar
`is_legado = false` explicitamente enquanto o default for true. Conferir contagens/checksums de OS Finalizadas,
assinaturas e custo (devem ficar identicos) e zero fotos orfas. Quando o Alembic entrar (PR-19), fazer baseline/stamp
com estes objetos e os mesmos nomes dos models.

## Decisoes e premissas (sinalizadas)
- **`Pendente => id_tecnico_atribuido IS NULL`** e **`status <> 'Aberto'`** ficam no 0002 (nao no 0001) para nao
  quebrar o backend antigo. Legado com tecnico NAO e alterado automaticamente (0003, depende do PO). Nada desatribui OS
  por desativacao de tecnico (**RN-08a pendente**).
- **`por_papel='admin'` para pausa legada sem autor** e uma INFERENCIA: o codigo antigo gravava `por_tecnico_id = NULL`
  quando o autor era admin. `por_usuario_id` fica NULL (admin desconhecido). `encerrada_em` das pausas legadas ja
  encerradas nao e preenchido (instante desconhecido).
- Os `hora_*` (HH:mm) **nao** sao convertidos para `*_em` automaticamente (exigiria assumir fuso/data); bloco opcional no 0003.
- `ordem_servico.is_completed` existe no banco, nenhum codigo a usa (nem o model): deprecada; remocao so no 0004.
- `pausa.por_tecnico_id` continua como coluna legada (nao mapeada no model; o attr `Pausa.por_tecnico_id` e um `synonym`
  de `por_usuario_id` para o codigo atual); remocao no 0004.
- Imutabilidade de `custo_os` (Q11) e regra de aplicacao; o banco nao bloqueia UPDATE nesta versao.
- RLS (0005): ligar sem policies bloqueia anon/authenticated; a API segue funcionando se o usuario do `DATABASE_URL` for
  `postgres`/dono ou tiver BYPASSRLS. Se nao for, a API perde acesso: testar antes.

## Inventario do banco remoto (projeto bsuehcxvnfawmabielhl, 2026-11-04, somente leitura)
- Sem migracoes registradas (`list_migrations` = []). Tabelas: tecnico 3 (2 admin, 1 tecnico), cliente 2, ordem_servico 2,
  visita 2, servico_equipamento 1, servico_defeito 1, servico_foto 7, material 1, comprovante 0, pausa 1.
- OS 1: `Pausado`, tecnico 3 (ativo), pausa ativa (Peca pendente, autor tecnico 3). OS 2: `Em Atendimento`, tecnico 3.
  **Nenhuma OS `Aberto`, nenhuma `Pendente`, nenhuma cancelada, nenhuma com tecnico inativo.** Logo `Aberto->Pendente` e o
  CHECK `Pendente => sem tecnico` nao afetam dados atuais.
- Enum `statuschamado`: Aberto, Agendado, Em Atendimento, Pendente, Finalizado, Aguardando Reagendamento, Pausado.
- `ordem_servico.is_completed` (BOOLEAN NOT NULL DEFAULT false) existe; todas as linhas `false`.
- `assinatura_cliente_url` e `text` (SDD: varchar(255)); nenhuma OS tem valor.
- Sem CHECKs de dominio; FKs sem indices de cobertura (advisor `unindexed_foreign_keys`, 10 FKs); so PKs e UNIQUEs
  (`cliente.codigo`, `tecnico.email`, `tecnico.cnpj`) existem.
- `km_total` NOT NULL sem default; varios NOT NULL sem default no banco (status, is_cancelled, em_garantia, ...).
- RLS desligado nas 10 tabelas (advisor ERROR `rls_disabled_in_public`; anon/authenticated com DML total). Donas: `postgres`
  (BYPASSRLS). Tambem alertas `pg_graphql_*_table_exposed`.
  **Atualizacao 11/11/2026:** situacao superada. Consulta a `pg_class` mostrou `relrowsecurity = true` em todas as 17
  tabelas de `public` (incluindo `equipamento_modelo`, `os_equipamento`, `sync_evento`, `sync_arquivo`, `log_acao`,
  `custo_os` e `configuracao_custo`) e `pg_policies` vazio: anon/authenticated sem acesso. A API segue funcionando (dono/BYPASSRLS).
- Arquivos: 11 referencias locais `/static/...` (7 em `visita`, 4 em `servico_foto`), 0 paths de Storage, 4 `url=''`
  (3 em `servico_foto`, 1 em `visita.foto_fim_volta_url`) - dados sujos; migracao para o bucket e tarefa do Backend (SDD 9).
- `visita 1` tem `hora_*` com `''` e `km_total=30` divergente da formula SDD (km_fim_volta NULL); legado de teste.
- Dados pessoais/credenciais nao foram lidos alem de id/role/is_active.

## Pendencias
Alembic (revisoes a partir destes SQL); teste dos scripts em Postgres limpo e em copia dos dados; decisao RN-08a; decisao
sobre `Aberto` com tecnico e `Pendente` com tecnico (se aparecerem); indice parcial unico de pausa ativa por visita (proposta,
nao incluida). Concluidos: RLS ligado e conferido (11/11/2026); migracao de arquivos para o Storage privado (0013 +
`scripts/migrar_arquivos_para_storage.py`, 09/11/2026).
