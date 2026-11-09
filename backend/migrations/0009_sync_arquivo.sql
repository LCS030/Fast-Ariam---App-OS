-- =============================================================================
-- 0009_sync_arquivo.sql  --  arquivos recebidos pela sincronizacao offline (SDD v0.5, 4.7 / 6.12)
--
-- Cria public.sync_arquivo: mapeia o client_file_id (gerado no aparelho) para a url gravada. A ligacao ao registro final
-- (foto de servico, odometro, comprovante, assinatura) so ocorre quando o evento que referencia o arquivo e aplicado.
-- Aditiva e idempotente; nao altera nenhuma tabela existente. Compativel com o backend antigo.
-- ESTA MIGRACAO NAO FOI APLICADA A NENHUM BANCO. Dev e producao compartilham o mesmo projeto Supabase (risco aceito pelo
-- PO): ensaiar em dump restaurado antes. Rollback: 0009_rollback.sql.
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico', 'ordem_servico', 'visita']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', t;
    END IF;
  END LOOP;
END
$mig$;

CREATE TABLE IF NOT EXISTS public.sync_arquivo (
  client_file_id uuid         PRIMARY KEY,
  id_tecnico     integer      NOT NULL,
  id_os          integer      NOT NULL,
  id_visita      integer      NOT NULL,
  tipo_arquivo   varchar(30)  NOT NULL,
  url            varchar(255) NOT NULL,
  recebido_em    timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT fk_sync_arquivo_id_tecnico FOREIGN KEY (id_tecnico) REFERENCES public.tecnico (id_tecnico),
  CONSTRAINT fk_sync_arquivo_id_os      FOREIGN KEY (id_os)      REFERENCES public.ordem_servico (id_os),
  CONSTRAINT fk_sync_arquivo_id_visita  FOREIGN KEY (id_visita)  REFERENCES public.visita (id_visita),
  CONSTRAINT ck_sync_arquivo_tipo CHECK (tipo_arquivo IN ('foto_defeito', 'foto_conserto', 'foto_deslocamento',
                                                          'comprovante_pedagio', 'comprovante_frete', 'assinatura'))
);

CREATE INDEX IF NOT EXISTS ix_sync_arquivo_id_tecnico ON public.sync_arquivo (id_tecnico);
CREATE INDEX IF NOT EXISTS ix_sync_arquivo_id_visita  ON public.sync_arquivo (id_visita);

-- Exposicao (SEG-12 / SEG-20): REVOKE sempre que os papeis do Supabase existirem; RLS (sem policies) so se o 0005 ja
-- estiver aplicado (usuario do DATABASE_URL ja validado) ou se a sessao declarar  SET fast_ariam.habilitar_rls = 'sim'.
DO $mig$
DECLARE
  v_forcar boolean := coalesce(current_setting('fast_ariam.habilitar_rls', true), '') = 'sim';
  v_rls_ja boolean;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON TABLE public.sync_arquivo FROM anon, authenticated;
  ELSE
    RAISE NOTICE '0009: papeis anon/authenticated inexistentes (nao e Supabase?); REVOKE ignorado.';
  END IF;

  SELECT c.relrowsecurity INTO v_rls_ja FROM pg_class c WHERE c.oid = 'public.ordem_servico'::regclass;
  IF v_forcar OR coalesce(v_rls_ja, false) THEN
    ALTER TABLE public.sync_arquivo ENABLE ROW LEVEL SECURITY;
    RAISE NOTICE '0009: RLS ligado (sem policies) em sync_arquivo.';
  ELSE
    RAISE NOTICE '0009: RLS NAO ligado em sync_arquivo. Quando confirmar o usuario do DATABASE_URL: ALTER TABLE public.sync_arquivo ENABLE ROW LEVEL SECURITY;';
  END IF;
END
$mig$;

COMMIT;

-- Pos-verificacao sugerida (somente leitura):
--   SELECT conname, convalidated FROM pg_constraint WHERE conrelid = 'public.sync_arquivo'::regclass;
--   Depois: get_advisors (security) no Supabase.
