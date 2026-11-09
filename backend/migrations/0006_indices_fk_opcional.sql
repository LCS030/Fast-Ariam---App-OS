-- =============================================================================
-- 0006_indices_fk_opcional.sql  --  indices de FK (OPCIONAL; nao aplicar sem validacao do Backend)
-- Evidencia: get_advisors(performance) = unindexed_foreign_keys (INFO) em 10 FKs. Hoje ha 2 OS, entao o
-- ganho e nulo; criar quando houver volume (SDD: meta p95 <= 2 s com 1.000 OS) e apos EXPLAIN (ANALYZE, BUFFERS)
-- das listagens reais. Em producao com dados, preferir CREATE INDEX CONCURRENTLY (fora de transacao).
-- Idempotente. ESTE ARQUIVO NAO FOI APLICADO A NENHUM BANCO PELO AGENTE DBA.
-- =============================================================================
CREATE INDEX IF NOT EXISTS ix_ordem_servico_id_tecnico_atribuido ON public.ordem_servico (id_tecnico_atribuido);
CREATE INDEX IF NOT EXISTS ix_ordem_servico_id_cliente           ON public.ordem_servico (id_cliente);
CREATE INDEX IF NOT EXISTS ix_ordem_servico_status               ON public.ordem_servico (status) WHERE NOT is_cancelled;
CREATE INDEX IF NOT EXISTS ix_visita_id_os                       ON public.visita (id_os);
CREATE INDEX IF NOT EXISTS ix_servico_equipamento_id_visita      ON public.servico_equipamento (id_visita);
CREATE INDEX IF NOT EXISTS ix_servico_defeito_id_servico         ON public.servico_defeito (id_servico);
CREATE INDEX IF NOT EXISTS ix_servico_foto_id_servico            ON public.servico_foto (id_servico);
CREATE INDEX IF NOT EXISTS ix_material_id_servico                ON public.material (id_servico);
CREATE INDEX IF NOT EXISTS ix_comprovante_id_visita              ON public.comprovante (id_visita);
CREATE INDEX IF NOT EXISTS ix_pausa_visita_id                    ON public.pausa (visita_id);
CREATE INDEX IF NOT EXISTS ix_pausa_por_usuario_id               ON public.pausa (por_usuario_id);
-- Rollback: DROP INDEX IF EXISTS public.ix_<nome>; para cada indice acima.
