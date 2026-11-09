-- =============================================================================
-- 0009_rollback.sql  --  desfaz 0009_sync_arquivo.sql
-- Remove SOMENTE a tabela sync_arquivo (mapa client_file_id -> url). Os arquivos fisicos NAO sao apagados e os registros ja
-- ligados (servico_foto, comprovante, visita) permanecem. Eventos de sincronizacao pendentes que referenciem arquivos
-- ficarao com ARQUIVO_AUSENTE ate o aparelho reenviar os arquivos.
-- =============================================================================
BEGIN;
DROP TABLE IF EXISTS public.sync_arquivo;
COMMIT;
