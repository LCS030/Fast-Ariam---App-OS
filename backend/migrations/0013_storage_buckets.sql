-- =============================================================================
-- 0013_storage_buckets.sql  --  buckets PRIVADOS do Supabase Storage para fotos, comprovantes e assinaturas cifradas
--
--   fast-ariam-privado      (producao)    fast-ariam-privado-dev (desenvolvimento; dev e producao compartilham o projeto)
--   public = false  |  limite 15 MB por arquivo  |  tipos: image/jpeg, image/png e application/octet-stream
--   (octet-stream = assinaturas .enc, cifradas pela aplicacao; a imagem real so e validada pela API com Pillow)
--
-- NENHUMA politica e criada em storage.objects: com RLS ativo isso NEGA qualquer acesso de anon/authenticated. Quem
-- acessa e SO o backend, com a chave de servico (que ignora RLS), depois de checar a permissao do usuario na OS.
-- Idempotente. Rollback: 0013_rollback.sql (so remove bucket VAZIO).
-- APLICADA no Supabase real em 08/11/2026 (MCP, migracao "0013_storage_buckets").
-- =============================================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('fast-ariam-privado',     'fast-ariam-privado',     false, 15728640, ARRAY['image/jpeg', 'image/png', 'application/octet-stream']),
  ('fast-ariam-privado-dev', 'fast-ariam-privado-dev', false, 15728640, ARRAY['image/jpeg', 'image/png', 'application/octet-stream'])
ON CONFLICT (id) DO NOTHING;
