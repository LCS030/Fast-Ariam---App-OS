-- =============================================================================
-- 0004_contracao_opcional.sql  --  fase "CONTRAIR" (OPCIONAL, DESTRUTIVA)
-- Remove colunas legadas sem uso depois que o Backend migrou:
--   * pausa.por_tecnico_id   (substituida por pausa.por_usuario_id)
--   * ordem_servico.is_completed (nenhum codigo do repositorio a referencia; semantica coberta por status/Finalizado)
-- NAO remove: ordem_servico.assinatura_cliente_url (historico), visita.nome_ajudante/telefone_ajudante (historico),
--             visita.hora_* (legado HH:mm ate os fronts migrarem).
--
-- Pre-condicoes (o script confere e ABORTA se nao cumpridas):
--   - 0001 aplicado; todas as pausas com por_tecnico_id tem por_usuario_id equivalente;
--   - is_completed nunca foi TRUE (senao ha informacao que nao esta em status).
-- Para executar apos o Backend confirmar que nao le/escreve por_tecnico_id nem is_completed.
-- Rollback: 0004_rollback.sql recria as colunas (VAZIAS para is_completed: o valor antigo nao e recuperavel
--   sem backup; por_tecnico_id e repovoada a partir de por_usuario_id para papel 'tecnico').
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='pausa' AND column_name='por_usuario_id') THEN
    RAISE EXCEPTION 'Aplique 0001 antes de 0004.';
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='pausa' AND column_name='por_tecnico_id') THEN
    IF EXISTS (SELECT 1 FROM public.pausa WHERE por_tecnico_id IS NOT NULL
                  AND por_usuario_id IS DISTINCT FROM por_tecnico_id) THEN
      RAISE EXCEPTION 'pausa: ha linhas em que por_usuario_id difere de por_tecnico_id; rode o backfill do 0001.';
    END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='ordem_servico' AND column_name='is_completed') THEN
    IF EXISTS (SELECT 1 FROM public.ordem_servico WHERE is_completed) THEN
      RAISE EXCEPTION 'ordem_servico.is_completed = TRUE em alguma linha: avaliar com o PO antes de remover.';
    END IF;
  END IF;
END
$mig$;

ALTER TABLE public.pausa DROP CONSTRAINT IF EXISTS pausa_por_tecnico_id_fkey;
ALTER TABLE public.pausa DROP COLUMN IF EXISTS por_tecnico_id;
ALTER TABLE public.ordem_servico DROP COLUMN IF EXISTS is_completed;

COMMIT;
