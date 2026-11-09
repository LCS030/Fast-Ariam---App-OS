-- =============================================================================
-- 0005_rollback.sql  --  desliga RLS (sem perda de dados). Se o REVOKE complementar do 0005 foi aplicado,
-- reconceder grants so se realmente necessario (nao recomendado: reexpoe as tabelas a anon/authenticated).
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
BEGIN;

DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico','cliente','ordem_servico','visita','servico_equipamento','servico_defeito',
                           'servico_foto','material','comprovante','pausa',
                           'configuracao_custo','custo_os','sync_evento','log_acao']
  LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END
$mig$;

COMMIT;
