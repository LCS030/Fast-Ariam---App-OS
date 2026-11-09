-- =============================================================================
-- 0012_cnpj_idx_obrigatorio.sql  --  torna tecnico.cnpj_idx NOT NULL
-- Rodar SO DEPOIS de scripts/cifrar_dados_existentes.py (que preenche cnpj_idx de todos os tecnicos). Aborta se sobrar NULL.
-- Rollback: 0012_rollback.sql
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '10s';
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.tecnico WHERE cnpj_idx IS NULL) THEN
    RAISE EXCEPTION 'Ha tecnico sem cnpj_idx. Rode scripts/cifrar_dados_existentes.py antes. Abortando.';
  END IF;
END
$mig$;
ALTER TABLE public.tecnico ALTER COLUMN cnpj_idx SET NOT NULL;
COMMIT;
