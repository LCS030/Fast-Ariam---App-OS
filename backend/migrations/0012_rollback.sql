-- Desfaz 0012_cnpj_idx_obrigatorio.sql
BEGIN;
ALTER TABLE public.tecnico ALTER COLUMN cnpj_idx DROP NOT NULL;
COMMIT;
