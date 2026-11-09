-- =============================================================================
-- 0010_integridade.sql  --  integridade: SHA-256 dos arquivos e selo HMAC da visita
--
-- ADITIVA e idempotente: so cria colunas anulaveis (o backend antigo continua funcionando sem elas).
--   sync_arquivo / servico_foto / comprovante : sha256            (hash dos bytes recebidos, calculado pelo servidor)
--   visita : assinatura_sha256 (hash da assinatura ANTES de cifrar), arquivos_sha256 (jsonb {campo_url: sha256} das fotos
--            de odometro/deslocamento), selo_integridade (HMAC-SHA256 em hex) e selo_versao (versao do esquema do selo)
-- Linhas existentes ficam com NULL: visitas finalizadas antes desta versao aparecem como "sem_selo" (nao sao seladas
-- retroativamente); scripts/cifrar_dados_existentes.py --hashes preenche os sha256 das fotos que ainda existem em disco.
-- Dev e producao compartilham o mesmo projeto Supabase: backup antes (scripts/backup_banco.py). Rollback: 0010_rollback.sql
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['sync_arquivo', 'servico_foto', 'comprovante', 'visita']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', t;
    END IF;
  END LOOP;
END
$mig$;

ALTER TABLE public.sync_arquivo ADD COLUMN IF NOT EXISTS sha256 varchar(64);
ALTER TABLE public.servico_foto ADD COLUMN IF NOT EXISTS sha256 varchar(64);
ALTER TABLE public.comprovante  ADD COLUMN IF NOT EXISTS sha256 varchar(64);

ALTER TABLE public.visita ADD COLUMN IF NOT EXISTS assinatura_sha256 varchar(64);
ALTER TABLE public.visita ADD COLUMN IF NOT EXISTS arquivos_sha256   jsonb;
ALTER TABLE public.visita ADD COLUMN IF NOT EXISTS selo_integridade  varchar(64);
ALTER TABLE public.visita ADD COLUMN IF NOT EXISTS selo_versao       integer;

-- Formato: 64 caracteres hexadecimais minusculos (ou NULL).
DO $mig$
DECLARE r record;
BEGIN
  FOR r IN SELECT * FROM (VALUES
      ('sync_arquivo', 'sha256',            'ck_sync_arquivo_sha256'),
      ('servico_foto', 'sha256',            'ck_servico_foto_sha256'),
      ('comprovante',  'sha256',            'ck_comprovante_sha256'),
      ('visita',       'assinatura_sha256', 'ck_visita_assinatura_sha256'),
      ('visita',       'selo_integridade',  'ck_visita_selo_integridade')
    ) AS v(tabela, coluna, nome)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = r.nome AND conrelid = ('public.' || r.tabela)::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (%I IS NULL OR %I ~ ''^[0-9a-f]{64}$'')',
                     r.tabela, r.nome, r.coluna, r.coluna);
    END IF;
  END LOOP;
END
$mig$;

COMMIT;
