-- =============================================================================
-- 0002_constraints_estado.sql  --  regras de estado da OS no banco (SDD 4.3 / 4.7 / 5)
-- Fase "CONTRAIR/ENDURECER". Aplicar SOMENTE depois de:
--   (1) 0001 aplicado;  (2) backend novo implantado (nao grava 'Aberto' nem 'Pendente' com tecnico,
--       preenche motivo_cancelamento ao cancelar e escreve pausa.por_usuario_id/por_papel);
--   (3) legado resolvido (0003_legado_manual.sql), conforme inventario do 0000_inventario.sql.
-- Se aplicado antes do backend novo, escritas da API que violem as regras falharao (erro 500).
--
-- Idempotente e transacional. As constraints sao criadas NOT VALID (enforcam toda escrita nova) e validadas
-- se o legado permitir; se nao, permanecem NOT VALID com WARNING (nao aborta, nao altera dados).
-- Regra RN-08a (desativar tecnico desatribui OS?) continua PENDENTE: este script nao desatribui nada.
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

-- Reexecucao segura do passo de legado "Aberto sem tecnico -> Pendente" (caso o backend antigo tenha gravado mais).
UPDATE public.ordem_servico SET status = 'Pendente'
 WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL;

DO $mig$
DECLARE r record; v_oid oid;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('ordem_servico', 'ck_os_pendente_sem_tecnico',
         $c$status <> 'Pendente' OR id_tecnico_atribuido IS NULL$c$),
      ('ordem_servico', 'ck_os_status_sem_aberto',
         $c$status <> 'Aberto'$c$),
      ('ordem_servico', 'ck_os_cancelamento_motivo',
         $c$NOT is_cancelled OR length(btrim(coalesce(motivo_cancelamento, ''))) > 0$c$)
    ) AS v(tbl, nome, def)
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I CHECK (%s) NOT VALID', r.tbl, r.nome, r.def);
    END IF;

    SELECT oid INTO v_oid FROM pg_constraint
     WHERE conname = r.nome AND conrelid = ('public.' || r.tbl)::regclass AND NOT convalidated;
    IF v_oid IS NOT NULL THEN
      BEGIN
        EXECUTE format('ALTER TABLE public.%I VALIDATE CONSTRAINT %I', r.tbl, r.nome);
      EXCEPTION WHEN check_violation THEN
        RAISE WARNING 'Constraint %.% permanece NOT VALID: ha linhas legadas violando a regra (veja 0000_inventario.sql / 0003_legado_manual.sql).',
                      r.tbl, r.nome;
      END;
    END IF;
  END LOOP;
END
$mig$;

-- pausa.por_papel NOT NULL (somente se o backfill do 0001 cobriu todas as linhas).
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.pausa WHERE por_papel IS NULL) THEN
    RAISE WARNING 'pausa.por_papel nao recebeu NOT NULL: existem linhas com NULL.';
  ELSE
    ALTER TABLE public.pausa ALTER COLUMN por_papel SET NOT NULL;
  END IF;
END
$mig$;

COMMIT;
