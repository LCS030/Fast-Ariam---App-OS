-- =============================================================================
-- aplicar_producao_completo.sql  --  Fast Ariam: limpeza dos dados de teste + schema SDD v0.3 + RLS fechado
-- Autorizado pelo PO em 2026-11-07 (banco so tem registros de teste; ambiente unico = producao).
-- COMO USAR: cole TUDO no SQL Editor do Supabase (projeto bsuehcxvnfawmabielhl) e execute UMA vez.
-- Tudo roda em UMA transacao: se algo falhar, nada e aplicado.
-- O QUE FAZ:
--   1) APAGA os dados de: comprovante, material, servico_defeito, servico_foto, servico_equipamento, pausa, visita,
--      ordem_servico, cliente (reinicia os ids). PRESERVA a tabela `tecnico` (contas de admin/tecnico para login).
--   2) Aplica 0001 (colunas/tabelas novas SDD 4.7), 0002 (CHECKs de estado) e 0005 (RLS ligado).
--   3) Fecha a exposicao do Supabase: REVOKE de anon/authenticated em todas as tabelas/sequencias de public e
--      privilegios padrao futuros. A API usa a conexao `postgres` (BYPASSRLS), entao NAO e afetada.
-- Depois de rodar, confira com as consultas de verificacao no fim do arquivo.
-- =============================================================================
BEGIN;

TRUNCATE TABLE public.comprovante, public.material, public.servico_defeito, public.servico_foto,
               public.servico_equipamento, public.pausa, public.visita, public.ordem_servico, public.cliente
  RESTART IDENTITY CASCADE;

-- ----------------------------- 0001_alinhar_sdd_v03.sql -----------------------------
-- =============================================================================
-- 0001_alinhar_sdd_v03.sql  --  Fast Ariam: alinhamento do modelo ao SDD v0.3 (secao 4.7)
-- Fase "EXPANDIR": somente adiciona colunas/tabelas/constraints e faz backfill seguro.
-- NAO remove nada (por_tecnico_id, is_completed, assinatura_cliente_url, ajudantes permanecem).
--
-- Idempotente: pode ser reexecutado sem efeito colateral.
-- Transacional: tudo-ou-nada (BEGIN/COMMIT). Nao usa ALTER TYPE ... ADD VALUE (nenhum valor novo de enum
--   e necessario: os 6 status de negocio ja existem em statuschamado; 'Aberto' permanece como valor legado).
-- Alvo: PostgreSQL 15+ (Supabase usa 17). Tabelas pequenas: ACCESS EXCLUSIVE breve e aceitavel.
--
-- ANTES DE EXECUTAR: backup/snapshot do banco e rodar 0000_inventario.sql (somente leitura).
-- Como executar (exemplo): psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 0001_alinhar_sdd_v03.sql
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA (so leitura no remoto).
-- =============================================================================

SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 0. Pre-requisitos
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico','cliente','ordem_servico','visita','servico_equipamento',
                           'servico_defeito','servico_foto','material','comprovante','pausa']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', t;
    END IF;
  END LOOP;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 1. ordem_servico: cancelamento (SDD 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.ordem_servico
  ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT,
  ADD COLUMN IF NOT EXISTS cancelado_em        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cancelado_por       INTEGER;

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'ordem_servico_cancelado_por_fkey'
                   AND conrelid = 'public.ordem_servico'::regclass) THEN
    ALTER TABLE public.ordem_servico
      ADD CONSTRAINT ordem_servico_cancelado_por_fkey
      FOREIGN KEY (cancelado_por) REFERENCES public.tecnico (id_tecnico);
  END IF;
END
$mig$;

-- Defaults do SDD 4.3 (metadado apenas; nao reescreve linhas).
ALTER TABLE public.ordem_servico ALTER COLUMN status       SET DEFAULT 'Pendente';
ALTER TABLE public.ordem_servico ALTER COLUMN is_cancelled SET DEFAULT false;
ALTER TABLE public.ordem_servico ALTER COLUMN em_garantia  SET DEFAULT true;

-- assinatura_cliente_url: DESCONTINUADA (PR-35). Tipo no SDD: VARCHAR(255); no banco hoje e TEXT.
-- So converte se nenhum valor excede 255 (nao trunca dados).
DO $mig$
DECLARE v_tipo text; v_max int;
BEGIN
  SELECT data_type INTO v_tipo FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'ordem_servico' AND column_name = 'assinatura_cliente_url';
  IF v_tipo = 'text' THEN
    SELECT coalesce(max(length(assinatura_cliente_url)), 0) INTO v_max FROM public.ordem_servico;
    IF v_max <= 255 THEN
      ALTER TABLE public.ordem_servico ALTER COLUMN assinatura_cliente_url TYPE VARCHAR(255);
    ELSE
      RAISE WARNING 'assinatura_cliente_url mantida como TEXT: existe valor com % caracteres (> 255).', v_max;
    END IF;
  END IF;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 2. Legado de status: 'Aberto' SEM tecnico -> 'Pendente' (PRD v0.3).
--    'Aberto' COM tecnico e 'Pendente' COM tecnico NAO sao alterados aqui (decisao de negocio pendente):
--    ver 0000_inventario.sql e 0003_legado_manual.sql.
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE r record; n_mig int := 0; n_aberto_tec int; n_pend_tec int;
BEGIN
  FOR r IN SELECT id_os FROM public.ordem_servico
            WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL ORDER BY id_os
  LOOP
    RAISE NOTICE 'OS % migrada Aberto -> Pendente (anote para eventual rollback manual)', r.id_os;
    n_mig := n_mig + 1;
  END LOOP;
  UPDATE public.ordem_servico SET status = 'Pendente'
   WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL;

  SELECT count(*) INTO n_aberto_tec FROM public.ordem_servico
   WHERE status = 'Aberto' AND id_tecnico_atribuido IS NOT NULL;
  SELECT count(*) INTO n_pend_tec FROM public.ordem_servico
   WHERE status = 'Pendente' AND id_tecnico_atribuido IS NOT NULL;
  RAISE NOTICE 'Aberto->Pendente: % OS. Pendentes de decisao: Aberto com tecnico = %, Pendente com tecnico = %.',
               n_mig, n_aberto_tec, n_pend_tec;
  IF n_aberto_tec + n_pend_tec > 0 THEN
    RAISE WARNING 'Existem OS legadas que violam "Pendente => sem tecnico"/"Aberto nao persistido". '
                  'Resolva (0003_legado_manual.sql) ANTES de aplicar 0002_constraints_estado.sql.';
  END IF;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 3. visita: assinatura, CPF e timestamps com fuso (SDD 4.4 / 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.visita
  ADD COLUMN IF NOT EXISTS assinatura_url          VARCHAR(255),
  ADD COLUMN IF NOT EXISTS nome_cliente_assinatura VARCHAR(100),
  ADD COLUMN IF NOT EXISTS documento_cliente       VARCHAR(11),
  ADD COLUMN IF NOT EXISTS ida_inicio_em           TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS ida_fim_em              TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS atendimento_inicio_em   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS atendimento_fim_em      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS volta_inicio_em         TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS volta_fim_em            TIMESTAMPTZ;

-- km_total: NOT NULL ja existe; falta DEFAULT 0 (SDD 4.4). Defensivo: nenhum NULL pode existir.
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.visita WHERE km_total IS NULL) THEN
    RAISE EXCEPTION 'visita.km_total contem NULL; corrija antes (nao inventamos valores).';
  END IF;
END
$mig$;
ALTER TABLE public.visita ALTER COLUMN km_total              SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN km_total              SET NOT NULL;
ALTER TABLE public.visita ALTER COLUMN valor_pedagio         SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN valor_frete_devolucao SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN servico_finalizado    SET DEFAULT false;

-- NOTA backfill: as colunas hora_* (HH:mm, sem data/fuso) NAO sao convertidas automaticamente para os
-- novos *_em: exigiria assumir fuso e a data de cada evento. Opcao assistida em 0003_legado_manual.sql.

-- -----------------------------------------------------------------------------
-- 4. pausa: autor (usuario + papel) e encerramento (SDD 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.pausa
  ADD COLUMN IF NOT EXISTS por_usuario_id INTEGER,
  ADD COLUMN IF NOT EXISTS por_papel      VARCHAR(10),
  ADD COLUMN IF NOT EXISTS encerrada_em   TIMESTAMPTZ;

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'pausa_por_usuario_id_fkey' AND conrelid = 'public.pausa'::regclass) THEN
    ALTER TABLE public.pausa
      ADD CONSTRAINT pausa_por_usuario_id_fkey
      FOREIGN KEY (por_usuario_id) REFERENCES public.tecnico (id_tecnico);
  END IF;
END
$mig$;

-- Backfill (somente linhas ainda nao preenchidas; seguro para reexecucao):
--  a) por_usuario_id := por_tecnico_id (a coluna legada permanece intacta);
UPDATE public.pausa SET por_usuario_id = por_tecnico_id
 WHERE por_usuario_id IS NULL AND por_tecnico_id IS NOT NULL;
--  b) por_papel := papel real do autor em tecnico.role;
UPDATE public.pausa p SET por_papel = t.role::text
  FROM public.tecnico t
 WHERE t.id_tecnico = p.por_usuario_id AND p.por_papel IS NULL;
--  c) INFERENCIA: o codigo legado (chamados.py) gravava por_tecnico_id = NULL quando o autor era admin.
--     Logo, pausa legada sem autor => papel 'admin' com usuario desconhecido (por_usuario_id fica NULL).
UPDATE public.pausa SET por_papel = 'admin'
 WHERE por_papel IS NULL AND por_usuario_id IS NULL;
--  d) encerrada_em das pausas legadas ja inativas NAO e preenchido (instante real desconhecido).

-- -----------------------------------------------------------------------------
-- 5. Novas tabelas (SDD 4.7)
-- -----------------------------------------------------------------------------
-- 5.1 configuracao_custo: configuracao GLOBAL, linha unica (sem FK para tecnico). NAO semeada.
CREATE TABLE IF NOT EXISTS public.configuracao_custo (
  id_configuracao            SMALLINT      PRIMARY KEY,
  primeira_hora_tecnico      NUMERIC(10,2) NOT NULL DEFAULT 0,
  hora_tecnico               NUMERIC(10,2) NOT NULL DEFAULT 0,
  tempo_deslocamento_tecnico NUMERIC(10,2) NOT NULL DEFAULT 0,
  quilometragem              NUMERIC(10,2) NOT NULL DEFAULT 0,
  atualizado_em              TIMESTAMPTZ   NOT NULL DEFAULT now(),
  CONSTRAINT ck_configuracao_custo_linha_unica CHECK (id_configuracao = 1),
  CONSTRAINT ck_configuracao_custo_valores_nao_negativos CHECK (
    primeira_hora_tecnico >= 0 AND hora_tecnico >= 0
    AND tempo_deslocamento_tecnico >= 0 AND quilometragem >= 0)
);

-- 5.2 custo_os: snapshot do custo na finalizacao (1 linha por OS)
CREATE TABLE IF NOT EXISTS public.custo_os (
  id_os              INTEGER       PRIMARY KEY REFERENCES public.ordem_servico (id_os),
  calculado_em       TIMESTAMPTZ   NOT NULL DEFAULT now(),
  total              NUMERIC(12,2) NOT NULL,
  detalhes           JSONB         NOT NULL,
  valores_utilizados JSONB         NOT NULL,
  CONSTRAINT ck_custo_os_total_nao_negativo CHECK (total >= 0)
);

-- 5.3 sync_evento: idempotencia da sincronizacao offline (client_event_id = chave)
CREATE TABLE IF NOT EXISTS public.sync_evento (
  client_event_id UUID         PRIMARY KEY,
  id_tecnico      INTEGER      NOT NULL REFERENCES public.tecnico (id_tecnico),
  id_os           INTEGER      REFERENCES public.ordem_servico (id_os),
  id_visita       INTEGER      REFERENCES public.visita (id_visita),
  tipo            VARCHAR(50)  NOT NULL,
  ocorrido_em     TIMESTAMPTZ  NOT NULL,
  recebido_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
  payload         JSONB        NOT NULL DEFAULT '{}'::jsonb,
  resultado       VARCHAR(12)  NOT NULL,
  codigo          VARCHAR(40),
  detalhe         TEXT,
  CONSTRAINT ck_sync_evento_resultado CHECK (resultado IN ('aplicado', 'duplicado', 'rejeitado'))
);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_os                  ON public.sync_evento (id_os);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_visita_ocorrido_em  ON public.sync_evento (id_visita, ocorrido_em);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_tecnico_recebido_em ON public.sync_evento (id_tecnico, recebido_em);

-- 5.4 log_acao: auditoria (id_usuario NULL e papel 'sistema' para acoes automaticas, ex. SY-05)
CREATE TABLE IF NOT EXISTS public.log_acao (
  id         BIGINT      GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  id_os      INTEGER     REFERENCES public.ordem_servico (id_os),
  id_usuario INTEGER     REFERENCES public.tecnico (id_tecnico),
  papel      VARCHAR(10),
  acao       VARCHAR(50) NOT NULL,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload    JSONB
);
CREATE INDEX IF NOT EXISTS ix_log_acao_id_os_criado_em ON public.log_acao (id_os, criado_em);
CREATE INDEX IF NOT EXISTS ix_log_acao_id_usuario      ON public.log_acao (id_usuario);

-- Exposicao: o Supabase concede DML a anon/authenticated em tabelas novas do schema public.
-- Revogamos nas tabelas novas (a API usa conexao direta com o dono da tabela; SEG-12). Sem impacto na API.
REVOKE ALL ON public.configuracao_custo, public.custo_os, public.sync_evento, public.log_acao
  FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 6. CHECKs (criados NOT VALID -> valem para toda escrita nova; depois valida se o legado permitir)
--    Se a validacao falhar, a constraint permanece NOT VALID e um WARNING e emitido (nao aborta).
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE r record; v_oid oid;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('servico_foto', 'ck_servico_foto_tipo',
         $c$tipo IN ('defeito', 'conserto')$c$),
      ('comprovante',  'ck_comprovante_tipo',
         $c$tipo IN ('pedagio', 'frete')$c$),
      ('visita',       'ck_visita_documento_cliente',
         $c$documento_cliente IS NULL OR documento_cliente ~ '^[0-9]{11}$'$c$),
      ('pausa',        'ck_pausa_por_papel',
         $c$por_papel IS NULL OR por_papel IN ('admin', 'tecnico')$c$),
      ('pausa',        'ck_pausa_motivo',
         $c$motivo IN ('Peça pendente', 'Cliente ausente', 'Condições inseguras', 'Aguardando aprovação', 'Outro')$c$),
      ('pausa',        'ck_pausa_outro_descricao',
         $c$motivo <> 'Outro' OR length(btrim(coalesce(descricao, ''))) > 0$c$),
      ('pausa',        'ck_pausa_ativa_sem_encerramento',
         $c$NOT is_ativa OR encerrada_em IS NULL$c$)
    ) AS v(tbl, nome, def)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (%s) NOT VALID', r.tbl, r.nome, r.def);
    END IF;

    SELECT oid INTO v_oid FROM pg_constraint
     WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass AND NOT convalidated;
    IF v_oid IS NOT NULL THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I', r.tbl, r.nome);
      EXCEPTION WHEN check_violation THEN
        RAISE WARNING 'Constraint %.% criada NOT VALID: linhas legadas violam a regra. Corrija os dados e rode VALIDATE CONSTRAINT.',
                      r.tbl, r.nome;
      END;
    END IF;
  END LOOP;
END
$mig$;


-- Pos-verificacao sugerida (somente leitura):
--   SELECT conrelid::regclass, conname, convalidated FROM pg_constraint
--    WHERE connamespace = 'public'::regnamespace AND contype = 'c' AND conname LIKE 'ck\_%' ESCAPE '\' ORDER BY 1,2;

-- ----------------------------- 0002_constraints_estado.sql -----------------------------
-- =============================================================================
-- 0002_constraints_estado.sql  --  regras de estado da OS no banco (SDD 4.3 / 4.7 / 5)
-- Fase "CONTRAIR/ENDURECER". Aplicar SOMENTE depois de:
--   (1) 0001 aplicado;  (2) backend novo implantado (nao grava 'Aberto' nem 'Pendente' com tecnico,
--       preenche motivo_cancelamento ao cancelar e escreve pausa.por_usuario_id/por_papel);
--   (3) legado resolvido (0003_legado_manual.sql), conforme inventario do 0000_inventario.sql.
-- Se aplicado antes do backend novo, escritas da API que violem as regras falharao (erro 500).
--
-- Idempotente e transacional. As constraints sao criadas NOT VALID (enforcam toda escrita nova) e validadas
-- se o legado permitir; se nao, permanecem NOT VALID com WARNING (nao aborta, nao altera dados).
-- Regra RN-08a (desativar tecnico desatribui OS?) continua PENDENTE: este script nao desatribui nada.
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================

SET LOCAL lock_timeout = '10s';

-- Reexecucao segura do passo de legado "Aberto sem tecnico -> Pendente" (caso o backend antigo tenha gravado mais).
UPDATE public.ordem_servico SET status = 'Pendente'
 WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL;

DO $mig$
DECLARE r record; v_oid oid;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('ordem_servico', 'ck_os_pendente_sem_tecnico',
         $c$status <> 'Pendente' OR id_tecnico_atribuido IS NULL$c$),
      ('ordem_servico', 'ck_os_status_sem_aberto',
         $c$status <> 'Aberto'$c$),
      ('ordem_servico', 'ck_os_cancelamento_motivo',
         $c$NOT is_cancelled OR length(btrim(coalesce(motivo_cancelamento, ''))) > 0$c$)
    ) AS v(tbl, nome, def)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (%s) NOT VALID', r.tbl, r.nome, r.def);
    END IF;

    SELECT oid INTO v_oid FROM pg_constraint
     WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass AND NOT convalidated;
    IF v_oid IS NOT NULL THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I', r.tbl, r.nome);
      EXCEPTION WHEN check_violation THEN
        RAISE WARNING 'Constraint %.% permanece NOT VALID: ha linhas legadas violando a regra (veja 0000_inventario.sql / 0003_legado_manual.sql).',
                      r.tbl, r.nome;
      END;
    END IF;
  END LOOP;
END
$mig$;

-- pausa.por_papel NOT NULL (somente se o backfill do 0001 cobriu todas as linhas).
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.pausa WHERE por_papel IS NULL) THEN
    RAISE WARNING 'pausa.por_papel nao recebeu NOT NULL: existem linhas com NULL.';
  ELSE
    ALTER TABLE public.pausa ALTER COLUMN por_papel SET NOT NULL;
  END IF;
END
$mig$;


-- ----------------------------- 0005_rls_opcional.sql -----------------------------
-- =============================================================================
-- 0005_rls_opcional.sql  --  SEG-12: RLS ligado, SEM policies, em todas as tabelas de public (OPCIONAL)
-- Motivo: o advisor do Supabase reporta rls_disabled_in_public (ERROR) nas 10 tabelas: com a anon key,
--   qualquer pessoa le/altera todas as linhas via PostgREST. Somente a API deve acessar o banco (AR-01).
--
-- IMPACTO (leia antes de aplicar):
--   * Com RLS ligado e nenhuma policy, os papeis anon/authenticated (PostgREST/GraphQL/SDK) ficam SEM acesso.
--     Nenhuma superficie do produto usa esses papeis (SEG-12; fronts nao acessam o Supabase).
--   * A API NAO e afetada SE a conexao do DATABASE_URL for um papel dono das tabelas ou com BYPASSRLS.
--     No banco remoto as tabelas pertencem a `postgres` (rolbypassrls = true). CONFIRME o usuario do
--     DATABASE_URL (ex.: postgres.<ref> no pooler = postgres). Se for outro papel sem BYPASSRLS, a API perde
--     acesso total -> testar em branch/staging primeiro. NAO usar FORCE ROW LEVEL SECURITY (bloquearia o dono).
--   * Se algum dia o painel/app passar a usar Supabase Auth/PostgREST, sera preciso criar policies explicitas.
--   * Rollback imediato e sem perda de dados: 0005_rollback.sql.
-- Idempotente. ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================

DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico','cliente','ordem_servico','visita','servico_equipamento','servico_defeito',
                           'servico_foto','material','comprovante','pausa',
                           'configuracao_custo','custo_os','sync_evento','log_acao']
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END
$mig$;

-- Complemento opcional (defesa em profundidade; remove tambem a exposicao no GraphQL - lints 0026/0027):
-- REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
-- REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
-- (service_role e postgres mantem acesso; o 0001 ja revoga nas 4 tabelas novas.)


-- ----------------------------- fechar exposicao (SEG-12) -----------------------------
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES    FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;

COMMIT;

-- ----------------------------- VERIFICACAO (rode depois, separado) -----------------------------
-- 1) RLS ligado em todas as 14 tabelas (esperado: rowsecurity = true em todas):
--    SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY 1;
-- 2) Nenhuma permissao para anon/authenticated (esperado: 0 linhas):
--    SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants
--     WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');
-- 3) CHECKs validados (esperado: convalidated = true em todos):
--    SELECT conrelid::regclass, conname, convalidated FROM pg_constraint
--     WHERE connamespace = 'public'::regnamespace AND contype = 'c' AND conname LIKE 'ck\_%' ESCAPE '\' ORDER BY 1, 2;
-- 4) Contas preservadas e tabelas de negocio vazias:
--    SELECT (SELECT count(*) FROM tecnico) tecnicos, (SELECT count(*) FROM cliente) clientes,
--           (SELECT count(*) FROM ordem_servico) os, (SELECT count(*) FROM visita) visitas;
