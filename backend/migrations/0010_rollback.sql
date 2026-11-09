-- =============================================================================
-- 0010_rollback.sql  --  desfaz 0010_integridade.sql
-- Remove SOMENTE as colunas de hash/selo (os arquivos e demais dados nao sao tocados). Os hashes e selos gravados
-- sao perdidos; refazer a 0010 NAO os recupera (rode antes um backup, scripts/backup_banco.py).
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '10s';

ALTER TABLE public.visita DROP CONSTRAINT IF EXISTS ck_visita_selo_integridade;
ALTER TABLE public.visita DROP CONSTRAINT IF EXISTS ck_visita_assinatura_sha256;
ALTER TABLE public.visita DROP COLUMN IF EXISTS selo_versao;
ALTER TABLE public.visita DROP COLUMN IF EXISTS selo_integridade;
ALTER TABLE public.visita DROP COLUMN IF EXISTS arquivos_sha256;
ALTER TABLE public.visita DROP COLUMN IF EXISTS assinatura_sha256;

ALTER TABLE public.comprovante  DROP CONSTRAINT IF EXISTS ck_comprovante_sha256;
ALTER TABLE public.servico_foto DROP CONSTRAINT IF EXISTS ck_servico_foto_sha256;
ALTER TABLE public.sync_arquivo DROP CONSTRAINT IF EXISTS ck_sync_arquivo_sha256;
ALTER TABLE public.comprovante  DROP COLUMN IF EXISTS sha256;
ALTER TABLE public.servico_foto DROP COLUMN IF EXISTS sha256;
ALTER TABLE public.sync_arquivo DROP COLUMN IF EXISTS sha256;
COMMIT;
