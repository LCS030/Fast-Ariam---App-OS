-- =============================================================================
-- 0001_rollback.sql  --  desfaz 0001_alinhar_sdd_v03.sql (pode PERDER DADOS gravados apos a migracao)
--
-- Protecao: se alguma coluna/tabela a remover contiver dados, o script ABORTA, a menos que a sessao declare:
--     SET fast_ariam.confirmar_perda_dados = 'sim';
-- (use `psql -c "SET ..."` na mesma sessao, ou coloque a linha acima antes do \i).
--
-- NAO desfaz: a migracao de dados Aberto -> Pendente (os ids foram impressos como NOTICE na execucao do 0001;
--   sem eles use o backup). Nao e destrutivo manter as OS como Pendente.
-- NAO desfaz: por_tecnico_id permanece (nunca foi removida pelo 0001).
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- Execute 0002_rollback.sql ANTES deste, se 0002 tiver sido aplicado.
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
DECLARE
  v_ok boolean := coalesce(current_setting('fast_ariam.confirmar_perda_dados', true), '') = 'sim';
  n bigint;
BEGIN
  IF v_ok THEN RETURN; END IF;

  IF to_regclass('public.custo_os') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.custo_os' INTO n;
    IF n > 0 THEN RAISE EXCEPTION 'custo_os tem % linha(s); confirme a perda com SET fast_ariam.confirmar_perda_dados = ''sim''', n; END IF;
  END IF;
  IF to_regclass('public.sync_evento') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.sync_evento' INTO n;
    IF n > 0 THEN RAISE EXCEPTION 'sync_evento tem % linha(s); confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')', n; END IF;
  END IF;
  IF to_regclass('public.log_acao') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.log_acao' INTO n;
    IF n > 0 THEN RAISE EXCEPTION 'log_acao tem % linha(s) de auditoria; confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')', n; END IF;
  END IF;
  IF to_regclass('public.configuracao_custo') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.configuracao_custo' INTO n;
    IF n > 0 THEN RAISE EXCEPTION 'configuracao_custo tem % linha(s); confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')', n; END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='visita' AND column_name='assinatura_url') THEN
    IF EXISTS (SELECT 1 FROM public.visita WHERE assinatura_url IS NOT NULL OR nome_cliente_assinatura IS NOT NULL
                  OR documento_cliente IS NOT NULL OR ida_inicio_em IS NOT NULL OR ida_fim_em IS NOT NULL
                  OR atendimento_inicio_em IS NOT NULL OR atendimento_fim_em IS NOT NULL
                  OR volta_inicio_em IS NOT NULL OR volta_fim_em IS NOT NULL) THEN
      RAISE EXCEPTION 'visita possui dados nas colunas novas (assinatura/CPF/timestamps); confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')';
    END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='ordem_servico' AND column_name='motivo_cancelamento') THEN
    IF EXISTS (SELECT 1 FROM public.ordem_servico WHERE motivo_cancelamento IS NOT NULL
                  OR cancelado_em IS NOT NULL OR cancelado_por IS NOT NULL) THEN
      RAISE EXCEPTION 'ordem_servico possui dados de cancelamento; confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')';
    END IF;
  END IF;
END
$mig$;

-- pausa: devolve o autor (tecnico) para a coluna legada, depois remove as colunas novas.
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='pausa' AND column_name='por_usuario_id')
     AND EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='pausa' AND column_name='por_tecnico_id') THEN
    UPDATE public.pausa SET por_tecnico_id = por_usuario_id
     WHERE por_tecnico_id IS NULL AND por_usuario_id IS NOT NULL AND por_papel = 'tecnico';
  END IF;
END
$mig$;
-- Pausas de admin com id conhecido: por_tecnico_id legado seguia a regra "NULL para admin"; nao copiar.

ALTER TABLE public.pausa
  DROP CONSTRAINT IF EXISTS ck_pausa_por_papel,
  DROP CONSTRAINT IF EXISTS ck_pausa_motivo,
  DROP CONSTRAINT IF EXISTS ck_pausa_outro_descricao,
  DROP CONSTRAINT IF EXISTS ck_pausa_ativa_sem_encerramento,
  DROP CONSTRAINT IF EXISTS pausa_por_usuario_id_fkey;
ALTER TABLE public.pausa
  DROP COLUMN IF EXISTS por_usuario_id,
  DROP COLUMN IF EXISTS por_papel,
  DROP COLUMN IF EXISTS encerrada_em;

-- visita
ALTER TABLE public.visita DROP CONSTRAINT IF EXISTS ck_visita_documento_cliente;
ALTER TABLE public.visita
  DROP COLUMN IF EXISTS assinatura_url,
  DROP COLUMN IF EXISTS nome_cliente_assinatura,
  DROP COLUMN IF EXISTS documento_cliente,
  DROP COLUMN IF EXISTS ida_inicio_em,
  DROP COLUMN IF EXISTS ida_fim_em,
  DROP COLUMN IF EXISTS atendimento_inicio_em,
  DROP COLUMN IF EXISTS atendimento_fim_em,
  DROP COLUMN IF EXISTS volta_inicio_em,
  DROP COLUMN IF EXISTS volta_fim_em;
ALTER TABLE public.visita ALTER COLUMN km_total              DROP DEFAULT;
ALTER TABLE public.visita ALTER COLUMN valor_pedagio         DROP DEFAULT;
ALTER TABLE public.visita ALTER COLUMN valor_frete_devolucao DROP DEFAULT;
ALTER TABLE public.visita ALTER COLUMN servico_finalizado    DROP DEFAULT;

-- CHECKs de tipo
ALTER TABLE public.servico_foto DROP CONSTRAINT IF EXISTS ck_servico_foto_tipo;
ALTER TABLE public.comprovante  DROP CONSTRAINT IF EXISTS ck_comprovante_tipo;

-- ordem_servico
ALTER TABLE public.ordem_servico DROP CONSTRAINT IF EXISTS ordem_servico_cancelado_por_fkey;
ALTER TABLE public.ordem_servico
  DROP COLUMN IF EXISTS motivo_cancelamento,
  DROP COLUMN IF EXISTS cancelado_em,
  DROP COLUMN IF EXISTS cancelado_por;
ALTER TABLE public.ordem_servico ALTER COLUMN status       DROP DEFAULT;
ALTER TABLE public.ordem_servico ALTER COLUMN is_cancelled DROP DEFAULT;
ALTER TABLE public.ordem_servico ALTER COLUMN em_garantia  DROP DEFAULT;
-- Tipo original da coluna legada no banco remoto era TEXT.
ALTER TABLE public.ordem_servico ALTER COLUMN assinatura_cliente_url TYPE TEXT;

-- Novas tabelas (ordem respeita FKs)
DROP TABLE IF EXISTS public.log_acao;
DROP TABLE IF EXISTS public.sync_evento;
DROP TABLE IF EXISTS public.custo_os;
DROP TABLE IF EXISTS public.configuracao_custo;

COMMIT;
