-- =============================================================================
-- 0005_rls_opcional.sql  --  SEG-12: RLS ligado, SEM policies, em todas as tabelas de public (OPCIONAL)
-- Motivo: o advisor do Supabase reporta rls_disabled_in_public (ERROR) nas 10 tabelas: com a anon key,
--   qualquer pessoa le/altera todas as linhas via PostgREST. Somente a API deve acessar o banco (AR-01).
--
-- IMPACTO (leia antes de aplicar):
--   * Com RLS ligado e nenhuma policy, os papeis anon/authenticated (PostgREST/GraphQL/SDK) ficam SEM acesso.
--     Nenhuma superficie do produto usa esses papeis (SEG-12; fronts nao acessam o Supabase).
--   * A API NAO e afetada SE a conexao do DATABASE_URL for um papel dono das tabelas ou com BYPASSRLS.
--     No banco remoto as tabelas pertencem a `postgres` (rolbypassrls = true). CONFIRME o usuario do
--     DATABASE_URL (ex.: postgres.<ref> no pooler = postgres). Se for outro papel sem BYPASSRLS, a API perde
--     acesso total -> testar em branch/staging primeiro. NAO usar FORCE ROW LEVEL SECURITY (bloquearia o dono).
--   * Se algum dia o painel/app passar a usar Supabase Auth/PostgREST, sera preciso criar policies explicitas.
--   * Rollback imediato e sem perda de dados: 0005_rollback.sql.
-- Idempotente. ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
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
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
  END LOOP;
END
$mig$;

-- Complemento opcional (defesa em profundidade; remove tambem a exposicao no GraphQL - lints 0026/0027):
-- REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
-- REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
-- (service_role e postgres mantem acesso; o 0001 ja revoga nas 4 tabelas novas.)

COMMIT;
