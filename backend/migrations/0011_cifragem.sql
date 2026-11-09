-- =============================================================================
-- 0011_cifragem.sql  --  prepara o banco para campos sensiveis CIFRADOS pela aplicacao (AES-256-GCM, prefixo "enc1:")
--
--   * tecnico.cnpj, cpf, telefone, banco, agencia, conta, pix  e  visita.documento_cliente  ->  TEXT
--     (o texto cifrado e bem maior que um CPF; varchar(11/14/18/20/...) nao comporta)
--   * remove ck_visita_documento_cliente (CPF = 11 digitos): nao se aplica a texto cifrado; a regra continua validada
--     no backend (cpf_valido) antes de cifrar
--   * remove tecnico_cnpj_key (UNIQUE em tecnico.cnpj): com nonce aleatorio o valor cifrado nunca se repete, entao o
--     UNIQUE perderia o sentido; a unicidade passa a ser do INDICE CEGO tecnico.cnpj_idx (HMAC-SHA256 dos 14 digitos)
--   * cria tecnico.cnpj_idx varchar(64) + indice UNIQUE (NULL permitido ate o script preencher; ver 0012)
--
-- NAO CIFRA OS DADOS: isso e feito por scripts/cifrar_dados_existentes.py (idempotente). Ordem OBRIGATORIA:
--   1) backup (scripts/backup_banco.py)   2) esta migracao   3) script   4) 0012_cnpj_idx_obrigatorio.sql
-- O backend novo le texto puro (legado) enquanto ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=true; depois do script, false.
-- ATENCAO: o backend ANTIGO (sem a cifragem) deixa de funcionar com valores cifrados. Dev e producao compartilham o
-- mesmo projeto Supabase. Rollback: 0011_rollback.sql (exige antes: python scripts/cifrar_dados_existentes.py --decifrar).
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico', 'visita']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', t;
    END IF;
  END LOOP;
END
$mig$;

ALTER TABLE public.visita  DROP CONSTRAINT IF EXISTS ck_visita_documento_cliente;
ALTER TABLE public.tecnico DROP CONSTRAINT IF EXISTS tecnico_cnpj_key;

ALTER TABLE public.tecnico
  ALTER COLUMN cnpj     TYPE text,
  ALTER COLUMN cpf      TYPE text,
  ALTER COLUMN telefone TYPE text,
  ALTER COLUMN banco    TYPE text,
  ALTER COLUMN agencia  TYPE text,
  ALTER COLUMN conta    TYPE text,
  ALTER COLUMN pix      TYPE text;

ALTER TABLE public.visita ALTER COLUMN documento_cliente TYPE text;

ALTER TABLE public.tecnico ADD COLUMN IF NOT EXISTS cnpj_idx varchar(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tecnico_cnpj_idx ON public.tecnico (cnpj_idx);

COMMIT;
