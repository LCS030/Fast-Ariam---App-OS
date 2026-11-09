-- =============================================================================
-- 0011_rollback.sql  --  desfaz 0011_cifragem.sql
-- PRE-REQUISITO: rodar `python scripts/cifrar_dados_existentes.py --decifrar` (volta os valores para texto puro). Sem
-- isso a migracao ABORTA: estreitar as colunas com texto cifrado dentro corromperia/recusaria os dados.
-- Depois disso defina ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=true ate o backend antigo estar no ar.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.tecnico WHERE cpf LIKE 'enc1:%' OR cnpj LIKE 'enc1:%' OR telefone LIKE 'enc1:%'
             OR banco LIKE 'enc1:%' OR agencia LIKE 'enc1:%' OR conta LIKE 'enc1:%' OR pix LIKE 'enc1:%')
     OR EXISTS (SELECT 1 FROM public.visita WHERE documento_cliente LIKE 'enc1:%') THEN
    RAISE EXCEPTION 'Ainda ha valores cifrados (enc1:). Rode scripts/cifrar_dados_existentes.py --decifrar antes. Abortando.';
  END IF;
END
$mig$;

DROP INDEX IF EXISTS public.uq_tecnico_cnpj_idx;
ALTER TABLE public.tecnico DROP COLUMN IF EXISTS cnpj_idx;

ALTER TABLE public.tecnico
  ALTER COLUMN cnpj     TYPE varchar(18),
  ALTER COLUMN cpf      TYPE varchar(14),
  ALTER COLUMN telefone TYPE varchar(20),
  ALTER COLUMN banco    TYPE varchar(100),
  ALTER COLUMN agencia  TYPE varchar(50),
  ALTER COLUMN conta    TYPE varchar(50),
  ALTER COLUMN pix      TYPE varchar(100);
ALTER TABLE public.visita ALTER COLUMN documento_cliente TYPE varchar(11);

ALTER TABLE public.tecnico ADD CONSTRAINT tecnico_cnpj_key UNIQUE (cnpj);
ALTER TABLE public.visita ADD CONSTRAINT ck_visita_documento_cliente
  CHECK (documento_cliente IS NULL OR documento_cliente ~ '^[0-9]{11}$') NOT VALID;
ALTER TABLE public.visita VALIDATE CONSTRAINT ck_visita_documento_cliente;
COMMIT;
