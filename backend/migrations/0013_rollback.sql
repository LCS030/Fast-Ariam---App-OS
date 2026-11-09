-- Desfaz 0013_storage_buckets.sql. O Supabase NAO deixa apagar bucket com objetos: esvazie-o antes
-- (scripts/migrar_arquivos_para_storage.py so COPIA; os originais locais ficam ate voce apagar com --apagar-locais).
DELETE FROM storage.buckets WHERE id IN ('fast-ariam-privado', 'fast-ariam-privado-dev');
