-- =====================================================================================================================
-- Fast Ariam v0.5  --  ROLLBACK PARA O SQL EDITOR (desfaz sql_editor_v05_aplicar.sql)
--
-- Ordem: 0009 (sync_arquivo) e depois 0007 (equipamentos). Numa unica transacao.
-- ATENCAO: remove as tabelas equipamento_modelo, os_equipamento e sync_arquivo e as colunas novas de servico_equipamento.
-- Se o sistema ja estiver gravando equipamentos (v0.5 em uso), o 0007_rollback ABORTA para proteger os dados; so confirme
-- a perda executando antes, na mesma execucao:   SET LOCAL fast_ariam.confirmar_perda_dados = 'sim';
-- Depois do go-live prefira corrigir para a frente (roll-forward).
-- Os arquivos fisicos enviados NAO sao apagados.
-- =====================================================================================================================
BEGIN;

-- ----- 0009_rollback -----
DROP TABLE IF EXISTS public.sync_arquivo;

-- ----- 0007_rollback -----
SET LOCAL lock_timeout = '10s';

-- 0. Guarda contra perda de dados pos-go-live
DO $mig$
DECLARE
  v_ok boolean := coalesce(current_setting('fast_ariam.confirmar_perda_dados', true), '') = 'sim';
  n bigint;
BEGIN
  IF v_ok THEN RETURN; END IF;

  IF to_regclass('public.os_equipamento') IS NOT NULL THEN
    EXECUTE $q$SELECT count(*) FROM public.os_equipamento WHERE origem <> 'backfill_legado'$q$ INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'os_equipamento tem % linha(s) com origem <> backfill_legado (criadas apos o go-live); confirme a perda com SET fast_ariam.confirmar_perda_dados = ''sim''', n;
    END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'servico_equipamento'
                AND column_name = 'conserto_salvo_em') THEN
    EXECUTE 'SELECT count(*) FROM public.servico_equipamento WHERE conserto_salvo_em IS NOT NULL' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'servico_equipamento tem % linha(s) com conserto_salvo_em preenchido; confirme a perda (SET fast_ariam.confirmar_perda_dados = ''sim'')', n;
    END IF;

    -- servicos sem serie legada: apos o rollback ficariam sem identificacao
    EXECUTE 'SELECT count(*) FROM public.servico_equipamento WHERE numero_serie_atendido IS NULL' INTO n;
    IF n > 0 THEN
      RAISE EXCEPTION 'servico_equipamento tem % linha(s) com numero_serie_atendido NULL (criadas pelo backend novo); o vinculo seria perdido; confirme (SET fast_ariam.confirmar_perda_dados = ''sim'')', n;
    END IF;
  END IF;

  IF to_regclass('public.equipamento_modelo') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.equipamento_modelo' INTO n;
    RAISE NOTICE '0007 rollback: o catalogo equipamento_modelo (% modelo(s)) sera descartado; modelos criados/editados pelo admin nao sao recuperaveis sem backup.', n;
  END IF;
END
$mig$;

-- 1. Trigger e funcao (antes das constraints/colunas)
DROP TRIGGER IF EXISTS trg_servico_equip_mesma_os ON public.servico_equipamento;
DROP FUNCTION IF EXISTS public.fn_servico_equip_mesma_os();

-- 2. Constraints (antes do UPDATE: ck_servico_equip_identificacao reprovaria linhas sem serie)
ALTER TABLE public.servico_equipamento
  DROP CONSTRAINT IF EXISTS ck_servico_equip_vinculo,
  DROP CONSTRAINT IF EXISTS ck_servico_equip_identificacao,
  DROP CONSTRAINT IF EXISTS uq_servico_equip_visita_os_equipamento,
  DROP CONSTRAINT IF EXISTS fk_servico_equipamento_id_os_equipamento;

-- 3. Desfaz o backfill do vinculo (so se as colunas ainda existem; execucao dinamica p/ reexecucao segura)
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'servico_equipamento'
                AND column_name = 'id_os_equipamento')
     AND EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'servico_equipamento'
                AND column_name = 'is_legado') THEN
    EXECUTE 'UPDATE public.servico_equipamento SET id_os_equipamento = NULL, is_legado = true
              WHERE id_os_equipamento IS NOT NULL OR is_legado IS DISTINCT FROM true';
  END IF;

  -- Apaga somente o que o backfill criou (o restante so some com a confirmacao + DROP TABLE adiante)
  IF to_regclass('public.os_equipamento') IS NOT NULL THEN
    EXECUTE $q$DELETE FROM public.os_equipamento WHERE origem = 'backfill_legado'$q$;
  END IF;
END
$mig$;

-- 4. Indice e colunas
DROP INDEX IF EXISTS public.ix_servico_equipamento_id_os_equipamento;
ALTER TABLE public.servico_equipamento
  DROP COLUMN IF EXISTS id_os_equipamento,
  DROP COLUMN IF EXISTS conserto_salvo_em,
  DROP COLUMN IF EXISTS is_legado;

-- 5. Tabelas novas (ordem respeita FKs; indices, sequences e RLS saem junto)
DROP TABLE IF EXISTS public.os_equipamento;
DROP TABLE IF EXISTS public.equipamento_modelo;

-- 6. Restaura NOT NULL de numero_serie_atendido SOMENTE se nao houver NULL (nao inventamos valores)
DO $mig$
DECLARE v_nullable boolean;
BEGIN
  SELECT (is_nullable = 'YES') INTO v_nullable
    FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'servico_equipamento'
     AND column_name = 'numero_serie_atendido';

  IF coalesce(v_nullable, false) THEN
    IF EXISTS (SELECT 1 FROM public.servico_equipamento WHERE numero_serie_atendido IS NULL) THEN
      RAISE WARNING '0007 rollback: numero_serie_atendido mantida ANULAVEL (existem linhas com NULL). Corrija os dados e rode: ALTER TABLE public.servico_equipamento ALTER COLUMN numero_serie_atendido SET NOT NULL;';
    ELSE
      ALTER TABLE public.servico_equipamento ALTER COLUMN numero_serie_atendido SET NOT NULL;
    END IF;
  END IF;
END
$mig$;

COMMIT;
