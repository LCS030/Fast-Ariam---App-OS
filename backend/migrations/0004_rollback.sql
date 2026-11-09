-- =============================================================================
-- 0004_rollback.sql  --  recria as colunas removidas por 0004_contracao_opcional.sql
-- Dados: is_completed volta como FALSE (valor original em todas as linhas inventariadas = false);
--        por_tecnico_id e repovoada de por_usuario_id apenas para papel 'tecnico'.
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
BEGIN;

ALTER TABLE public.ordem_servico ADD COLUMN IF NOT EXISTS is_completed BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.pausa ADD COLUMN IF NOT EXISTS por_tecnico_id INTEGER;

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'pausa_por_tecnico_id_fkey' AND conrelid = 'public.pausa'::regclass) THEN
    ALTER TABLE public.pausa ADD CONSTRAINT pausa_por_tecnico_id_fkey
      FOREIGN KEY (por_tecnico_id) REFERENCES public.tecnico (id_tecnico);
  END IF;
END
$mig$;

UPDATE public.pausa SET por_tecnico_id = por_usuario_id
 WHERE por_tecnico_id IS NULL AND por_usuario_id IS NOT NULL AND por_papel = 'tecnico';

COMMIT;
