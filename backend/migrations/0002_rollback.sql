-- =============================================================================
-- 0002_rollback.sql  --  desfaz 0002_constraints_estado.sql (sem perda de dados; so remove regras)
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
BEGIN;

ALTER TABLE public.ordem_servico
  DROP CONSTRAINT IF EXISTS ck_os_pendente_sem_tecnico,
  DROP CONSTRAINT IF EXISTS ck_os_status_sem_aberto,
  DROP CONSTRAINT IF EXISTS ck_os_cancelamento_motivo;

ALTER TABLE public.pausa ALTER COLUMN por_papel DROP NOT NULL;

COMMIT;
