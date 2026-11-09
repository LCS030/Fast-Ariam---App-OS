-- =============================================================================
-- 0001_alinhar_sdd_v03.sql  --  Fast Ariam: alinhamento do modelo ao SDD v0.3 (secao 4.7)
-- Fase "EXPANDIR": somente adiciona colunas/tabelas/constraints e faz backfill seguro.
-- NAO remove nada (por_tecnico_id, is_completed, assinatura_cliente_url, ajudantes permanecem).
--
-- Idempotente: pode ser reexecutado sem efeito colateral.
-- Transacional: tudo-ou-nada (BEGIN/COMMIT). Nao usa ALTER TYPE ... ADD VALUE (nenhum valor novo de enum
--   e necessario: os 6 status de negocio ja existem em statuschamado; 'Aberto' permanece como valor legado).
-- Alvo: PostgreSQL 15+ (Supabase usa 17). Tabelas pequenas: ACCESS EXCLUSIVE breve e aceitavel.
--
-- ANTES DE EXECUTAR: backup/snapshot do banco e rodar 0000_inventario.sql (somente leitura).
-- Como executar (exemplo): psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 0001_alinhar_sdd_v03.sql
-- ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA (so leitura no remoto).
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

-- -----------------------------------------------------------------------------
-- 0. Pre-requisitos
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tecnico','cliente','ordem_servico','visita','servico_equipamento',
                           'servico_defeito','servico_foto','material','comprovante','pausa']
  LOOP
    IF to_regclass('public.' || t) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', t;
    END IF;
  END LOOP;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 1. ordem_servico: cancelamento (SDD 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.ordem_servico
  ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT,
  ADD COLUMN IF NOT EXISTS cancelado_em        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cancelado_por       INTEGER;

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'ordem_servico_cancelado_por_fkey'
                   AND conrelid = 'public.ordem_servico'::regclass) THEN
    ALTER TABLE public.ordem_servico
      ADD CONSTRAINT ordem_servico_cancelado_por_fkey
      FOREIGN KEY (cancelado_por) REFERENCES public.tecnico (id_tecnico);
  END IF;
END
$mig$;

-- Defaults do SDD 4.3 (metadado apenas; nao reescreve linhas).
ALTER TABLE public.ordem_servico ALTER COLUMN status       SET DEFAULT 'Pendente';
ALTER TABLE public.ordem_servico ALTER COLUMN is_cancelled SET DEFAULT false;
ALTER TABLE public.ordem_servico ALTER COLUMN em_garantia  SET DEFAULT true;

-- assinatura_cliente_url: DESCONTINUADA (PR-35). Tipo no SDD: VARCHAR(255); no banco hoje e TEXT.
-- So converte se nenhum valor excede 255 (nao trunca dados).
DO $mig$
DECLARE v_tipo text; v_max int;
BEGIN
  SELECT data_type INTO v_tipo FROM information_schema.columns
   WHERE table_schema = 'public' AND table_name = 'ordem_servico' AND column_name = 'assinatura_cliente_url';
  IF v_tipo = 'text' THEN
    SELECT coalesce(max(length(assinatura_cliente_url)), 0) INTO v_max FROM public.ordem_servico;
    IF v_max <= 255 THEN
      ALTER TABLE public.ordem_servico ALTER COLUMN assinatura_cliente_url TYPE VARCHAR(255);
    ELSE
      RAISE WARNING 'assinatura_cliente_url mantida como TEXT: existe valor com % caracteres (> 255).', v_max;
    END IF;
  END IF;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 2. Legado de status: 'Aberto' SEM tecnico -> 'Pendente' (PRD v0.3).
--    'Aberto' COM tecnico e 'Pendente' COM tecnico NAO sao alterados aqui (decisao de negocio pendente):
--    ver 0000_inventario.sql e 0003_legado_manual.sql.
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE r record; n_mig int := 0; n_aberto_tec int; n_pend_tec int;
BEGIN
  FOR r IN SELECT id_os FROM public.ordem_servico
            WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL ORDER BY id_os
  LOOP
    RAISE NOTICE 'OS % migrada Aberto -> Pendente (anote para eventual rollback manual)', r.id_os;
    n_mig := n_mig + 1;
  END LOOP;
  UPDATE public.ordem_servico SET status = 'Pendente'
   WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL;

  SELECT count(*) INTO n_aberto_tec FROM public.ordem_servico
   WHERE status = 'Aberto' AND id_tecnico_atribuido IS NOT NULL;
  SELECT count(*) INTO n_pend_tec FROM public.ordem_servico
   WHERE status = 'Pendente' AND id_tecnico_atribuido IS NOT NULL;
  RAISE NOTICE 'Aberto->Pendente: % OS. Pendentes de decisao: Aberto com tecnico = %, Pendente com tecnico = %.',
               n_mig, n_aberto_tec, n_pend_tec;
  IF n_aberto_tec + n_pend_tec > 0 THEN
    RAISE WARNING 'Existem OS legadas que violam "Pendente => sem tecnico"/"Aberto nao persistido". '
                  'Resolva (0003_legado_manual.sql) ANTES de aplicar 0002_constraints_estado.sql.';
  END IF;
END
$mig$;

-- -----------------------------------------------------------------------------
-- 3. visita: assinatura, CPF e timestamps com fuso (SDD 4.4 / 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.visita
  ADD COLUMN IF NOT EXISTS assinatura_url          VARCHAR(255),
  ADD COLUMN IF NOT EXISTS nome_cliente_assinatura VARCHAR(100),
  ADD COLUMN IF NOT EXISTS documento_cliente       VARCHAR(11),
  ADD COLUMN IF NOT EXISTS ida_inicio_em           TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS ida_fim_em              TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS atendimento_inicio_em   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS atendimento_fim_em      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS volta_inicio_em         TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS volta_fim_em            TIMESTAMPTZ;

-- km_total: NOT NULL ja existe; falta DEFAULT 0 (SDD 4.4). Defensivo: nenhum NULL pode existir.
DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.visita WHERE km_total IS NULL) THEN
    RAISE EXCEPTION 'visita.km_total contem NULL; corrija antes (nao inventamos valores).';
  END IF;
END
$mig$;
ALTER TABLE public.visita ALTER COLUMN km_total              SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN km_total              SET NOT NULL;
ALTER TABLE public.visita ALTER COLUMN valor_pedagio         SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN valor_frete_devolucao SET DEFAULT 0;
ALTER TABLE public.visita ALTER COLUMN servico_finalizado    SET DEFAULT false;

-- NOTA backfill: as colunas hora_* (HH:mm, sem data/fuso) NAO sao convertidas automaticamente para os
-- novos *_em: exigiria assumir fuso e a data de cada evento. Opcao assistida em 0003_legado_manual.sql.

-- -----------------------------------------------------------------------------
-- 4. pausa: autor (usuario + papel) e encerramento (SDD 4.7)
-- -----------------------------------------------------------------------------
ALTER TABLE public.pausa
  ADD COLUMN IF NOT EXISTS por_usuario_id INTEGER,
  ADD COLUMN IF NOT EXISTS por_papel      VARCHAR(10),
  ADD COLUMN IF NOT EXISTS encerrada_em   TIMESTAMPTZ;

DO $mig$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'pausa_por_usuario_id_fkey' AND conrelid = 'public.pausa'::regclass) THEN
    ALTER TABLE public.pausa
      ADD CONSTRAINT pausa_por_usuario_id_fkey
      FOREIGN KEY (por_usuario_id) REFERENCES public.tecnico (id_tecnico);
  END IF;
END
$mig$;

-- Backfill (somente linhas ainda nao preenchidas; seguro para reexecucao):
--  a) por_usuario_id := por_tecnico_id (a coluna legada permanece intacta);
UPDATE public.pausa SET por_usuario_id = por_tecnico_id
 WHERE por_usuario_id IS NULL AND por_tecnico_id IS NOT NULL;
--  b) por_papel := papel real do autor em tecnico.role;
UPDATE public.pausa p SET por_papel = t.role::text
  FROM public.tecnico t
 WHERE t.id_tecnico = p.por_usuario_id AND p.por_papel IS NULL;
--  c) INFERENCIA: o codigo legado (chamados.py) gravava por_tecnico_id = NULL quando o autor era admin.
--     Logo, pausa legada sem autor => papel 'admin' com usuario desconhecido (por_usuario_id fica NULL).
UPDATE public.pausa SET por_papel = 'admin'
 WHERE por_papel IS NULL AND por_usuario_id IS NULL;
--  d) encerrada_em das pausas legadas ja inativas NAO e preenchido (instante real desconhecido).

-- -----------------------------------------------------------------------------
-- 5. Novas tabelas (SDD 4.7)
-- -----------------------------------------------------------------------------
-- 5.1 configuracao_custo: configuracao GLOBAL, linha unica (sem FK para tecnico). NAO semeada.
CREATE TABLE IF NOT EXISTS public.configuracao_custo (
  id_configuracao            SMALLINT      PRIMARY KEY,
  primeira_hora_tecnico      NUMERIC(10,2) NOT NULL DEFAULT 0,
  hora_tecnico               NUMERIC(10,2) NOT NULL DEFAULT 0,
  tempo_deslocamento_tecnico NUMERIC(10,2) NOT NULL DEFAULT 0,
  quilometragem              NUMERIC(10,2) NOT NULL DEFAULT 0,
  atualizado_em              TIMESTAMPTZ   NOT NULL DEFAULT now(),
  CONSTRAINT ck_configuracao_custo_linha_unica CHECK (id_configuracao = 1),
  CONSTRAINT ck_configuracao_custo_valores_nao_negativos CHECK (
    primeira_hora_tecnico >= 0 AND hora_tecnico >= 0
    AND tempo_deslocamento_tecnico >= 0 AND quilometragem >= 0)
);

-- 5.2 custo_os: snapshot do custo na finalizacao (1 linha por OS)
CREATE TABLE IF NOT EXISTS public.custo_os (
  id_os              INTEGER       PRIMARY KEY REFERENCES public.ordem_servico (id_os),
  calculado_em       TIMESTAMPTZ   NOT NULL DEFAULT now(),
  total              NUMERIC(12,2) NOT NULL,
  detalhes           JSONB         NOT NULL,
  valores_utilizados JSONB         NOT NULL,
  CONSTRAINT ck_custo_os_total_nao_negativo CHECK (total >= 0)
);

-- 5.3 sync_evento: idempotencia da sincronizacao offline (client_event_id = chave)
CREATE TABLE IF NOT EXISTS public.sync_evento (
  client_event_id UUID         PRIMARY KEY,
  id_tecnico      INTEGER      NOT NULL REFERENCES public.tecnico (id_tecnico),
  id_os           INTEGER      REFERENCES public.ordem_servico (id_os),
  id_visita       INTEGER      REFERENCES public.visita (id_visita),
  tipo            VARCHAR(50)  NOT NULL,
  ocorrido_em     TIMESTAMPTZ  NOT NULL,
  recebido_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
  payload         JSONB        NOT NULL DEFAULT '{}'::jsonb,
  resultado       VARCHAR(12)  NOT NULL,
  codigo          VARCHAR(40),
  detalhe         TEXT,
  CONSTRAINT ck_sync_evento_resultado CHECK (resultado IN ('aplicado', 'duplicado', 'rejeitado'))
);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_os                  ON public.sync_evento (id_os);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_visita_ocorrido_em  ON public.sync_evento (id_visita, ocorrido_em);
CREATE INDEX IF NOT EXISTS ix_sync_evento_id_tecnico_recebido_em ON public.sync_evento (id_tecnico, recebido_em);

-- 5.4 log_acao: auditoria (id_usuario NULL e papel 'sistema' para acoes automaticas, ex. SY-05)
CREATE TABLE IF NOT EXISTS public.log_acao (
  id         BIGINT      GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  id_os      INTEGER     REFERENCES public.ordem_servico (id_os),
  id_usuario INTEGER     REFERENCES public.tecnico (id_tecnico),
  papel      VARCHAR(10),
  acao       VARCHAR(50) NOT NULL,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload    JSONB
);
CREATE INDEX IF NOT EXISTS ix_log_acao_id_os_criado_em ON public.log_acao (id_os, criado_em);
CREATE INDEX IF NOT EXISTS ix_log_acao_id_usuario      ON public.log_acao (id_usuario);

-- Exposicao: o Supabase concede DML a anon/authenticated em tabelas novas do schema public.
-- Revogamos nas tabelas novas (a API usa conexao direta com o dono da tabela; SEG-12). Sem impacto na API.
REVOKE ALL ON public.configuracao_custo, public.custo_os, public.sync_evento, public.log_acao
  FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 6. CHECKs (criados NOT VALID -> valem para toda escrita nova; depois valida se o legado permitir)
--    Se a validacao falhar, a constraint permanece NOT VALID e um WARNING e emitido (nao aborta).
-- -----------------------------------------------------------------------------
DO $mig$
DECLARE r record; v_oid oid;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('servico_foto', 'ck_servico_foto_tipo',
         $c$tipo IN ('defeito', 'conserto')$c$),
      ('comprovante',  'ck_comprovante_tipo',
         $c$tipo IN ('pedagio', 'frete')$c$),
      ('visita',       'ck_visita_documento_cliente',
         $c$documento_cliente IS NULL OR documento_cliente ~ '^[0-9]{11}$'$c$),
      ('pausa',        'ck_pausa_por_papel',
         $c$por_papel IS NULL OR por_papel IN ('admin', 'tecnico')$c$),
      ('pausa',        'ck_pausa_motivo',
         $c$motivo IN ('Peça pendente', 'Cliente ausente', 'Condições inseguras', 'Aguardando aprovação', 'Outro')$c$),
      ('pausa',        'ck_pausa_outro_descricao',
         $c$motivo <> 'Outro' OR length(btrim(coalesce(descricao, ''))) > 0$c$),
      ('pausa',        'ck_pausa_ativa_sem_encerramento',
         $c$NOT is_ativa OR encerrada_em IS NULL$c$)
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
        RAISE WARNING 'Constraint %.% criada NOT VALID: linhas legadas violam a regra. Corrija os dados e rode VALIDATE CONSTRAINT.',
                      r.tbl, r.nome;
      END;
    END IF;
  END LOOP;
END
$mig$;

COMMIT;

-- Pos-verificacao sugerida (somente leitura):
--   SELECT conrelid::regclass, conname, convalidated FROM pg_constraint
--    WHERE connamespace = 'public'::regnamespace AND contype = 'c' AND conname LIKE 'ck\_%' ESCAPE '\' ORDER BY 1,2;
