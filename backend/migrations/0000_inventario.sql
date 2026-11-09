-- =============================================================================
-- 0000_inventario.sql  --  INVENTARIO SOMENTE LEITURA (nenhum DDL/DML). Rodar antes e depois das migracoes.
-- Cada consulta responde a um item do PRD/SDD v0.3. Resultado esperado "limpo" = 0 linhas nos blocos B, C, D.
-- =============================================================================

-- A. Contagens por tabela
SELECT 'tecnico' AS tabela, count(*) FROM public.tecnico
UNION ALL SELECT 'cliente', count(*) FROM public.cliente
UNION ALL SELECT 'ordem_servico', count(*) FROM public.ordem_servico
UNION ALL SELECT 'visita', count(*) FROM public.visita
UNION ALL SELECT 'servico_equipamento', count(*) FROM public.servico_equipamento
UNION ALL SELECT 'servico_defeito', count(*) FROM public.servico_defeito
UNION ALL SELECT 'servico_foto', count(*) FROM public.servico_foto
UNION ALL SELECT 'material', count(*) FROM public.material
UNION ALL SELECT 'comprovante', count(*) FROM public.comprovante
UNION ALL SELECT 'pausa', count(*) FROM public.pausa;

-- B. Distribuicao de status e atribuicao (PRD: inventariar Aberto/Pendente com tecnico)
SELECT status::text, is_cancelled, (id_tecnico_atribuido IS NOT NULL) AS tem_tecnico, count(*)
  FROM public.ordem_servico GROUP BY 1,2,3 ORDER BY 1,2,3;

-- B1. 'Aberto' SEM tecnico  -> migrado automaticamente para 'Pendente' (0001/0002)
SELECT id_os, status::text, id_tecnico_atribuido, data_abertura, data_agendamento
  FROM public.ordem_servico WHERE status = 'Aberto' AND id_tecnico_atribuido IS NULL;

-- B2. 'Aberto' COM tecnico  -> DECISAO DE NEGOCIO (proposta: Agendado se tecnico ativo); ver 0003
SELECT o.id_os, o.status::text, o.id_tecnico_atribuido, t.is_active AS tecnico_ativo, o.data_agendamento
  FROM public.ordem_servico o JOIN public.tecnico t ON t.id_tecnico = o.id_tecnico_atribuido
 WHERE o.status = 'Aberto';

-- B3. 'Pendente' COM tecnico -> viola "Pendente => sem tecnico" (bloqueia VALIDATE do 0002); ver 0003
SELECT o.id_os, o.status::text, o.id_tecnico_atribuido, t.is_active AS tecnico_ativo,
       o.data_agendamento, (SELECT count(*) FROM public.visita v WHERE v.id_os = o.id_os) AS visitas
  FROM public.ordem_servico o JOIN public.tecnico t ON t.id_tecnico = o.id_tecnico_atribuido
 WHERE o.status = 'Pendente';

-- B4. OS atribuidas a tecnico INATIVO (insumo para a decisao RN-08a; nada e desatribuido automaticamente)
SELECT o.id_os, o.status::text, o.id_tecnico_atribuido
  FROM public.ordem_servico o JOIN public.tecnico t ON t.id_tecnico = o.id_tecnico_atribuido
 WHERE NOT t.is_active AND o.status <> 'Finalizado' AND NOT o.is_cancelled;

-- C. Cancelamento: canceladas sem motivo (bloqueia ck_os_cancelamento_motivo)
SELECT id_os, status::text FROM public.ordem_servico
 WHERE is_cancelled AND length(btrim(coalesce(motivo_cancelamento, ''))) = 0;  -- exige 0001 aplicado

-- D. Coluna legada is_completed (existe no banco; nenhum codigo do repositorio a referencia)
SELECT is_completed, status::text, count(*) FROM public.ordem_servico GROUP BY 1,2 ORDER BY 1,2;

-- E. Valores de CHECK futuros
SELECT 'servico_foto.tipo' AS regra, tipo, count(*) FROM public.servico_foto GROUP BY 2
  HAVING tipo NOT IN ('defeito','conserto')
UNION ALL
SELECT 'comprovante.tipo', tipo, count(*) FROM public.comprovante GROUP BY 2
  HAVING tipo NOT IN ('pedagio','frete')
UNION ALL
SELECT 'pausa.motivo', motivo, count(*) FROM public.pausa GROUP BY 2
  HAVING motivo NOT IN ('Peça pendente','Cliente ausente','Condições inseguras','Aguardando aprovação','Outro');

-- F. Pausas: autor legado e ativas por visita
SELECT p.id_pausa, p.visita_id, p.motivo, p.is_ativa, p.por_tecnico_id, t.role::text AS papel_autor
  FROM public.pausa p LEFT JOIN public.tecnico t ON t.id_tecnico = p.por_tecnico_id ORDER BY 1;
SELECT visita_id, count(*) AS pausas_ativas FROM public.pausa WHERE is_ativa GROUP BY 1 HAVING count(*) > 1;

-- G. Referencias de arquivos (SDD 9: inventario antes de migrar para o Storage)
SELECT 'visita.foto/odometro' AS origem, count(*) FILTER (WHERE v IS NULL)              AS nulos,
       count(*) FILTER (WHERE v = '')                                                  AS vazios,
       count(*) FILTER (WHERE v LIKE '/static/%')                                      AS caminho_local,
       count(*) FILTER (WHERE v LIKE 'chamados/%')                                     AS path_storage
  FROM (SELECT unnest(ARRAY[odometro_inicio_url, odometro_fim_url, foto_inicio_ida_url, foto_fim_ida_url,
                            foto_inicio_volta_url, foto_fim_volta_url]) AS v FROM public.visita) s
UNION ALL
SELECT 'servico_foto.url', 0, count(*) FILTER (WHERE url = ''), count(*) FILTER (WHERE url LIKE '/static/%'),
       count(*) FILTER (WHERE url LIKE 'chamados/%') FROM public.servico_foto
UNION ALL
SELECT 'comprovante.url', 0, count(*) FILTER (WHERE url = ''), count(*) FILTER (WHERE url LIKE '/static/%'),
       count(*) FILTER (WHERE url LIKE 'chamados/%') FROM public.comprovante;

-- H. Horarios legados HH:mm invalidos / vazios ('' em vez de NULL) -- qualidade de dados
SELECT id_visita, hora_inicio_deslocamento, hora_chegada_cliente, hora_inicio_atendimento, hora_fim_atendimento,
       hora_inicio_ida, hora_fim_ida, hora_inicio_volta, hora_fim_volta
  FROM public.visita
 WHERE 'x' = ANY (SELECT CASE WHEN h = '' OR h !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' THEN 'x' END
                    FROM unnest(ARRAY[hora_inicio_deslocamento, hora_chegada_cliente, hora_inicio_atendimento,
                                      hora_fim_atendimento, hora_inicio_ida, hora_fim_ida, hora_inicio_volta,
                                      hora_fim_volta]) h WHERE h IS NOT NULL);

-- I. km_total versus formula do SDD 4.7: (km_fim_ida - km_inicio_ida) + (km_fim_volta - km_inicio_volta)
SELECT id_visita, km_total,
       (coalesce(km_fim_ida,0) - coalesce(km_inicio_ida,0)) + (coalesce(km_fim_volta,0) - coalesce(km_inicio_volta,0)) AS km_formula,
       km_inicio_ida, km_fim_ida, km_inicio_volta, km_fim_volta
  FROM public.visita ORDER BY 1;  -- divergencias sao dado legado; o backend recalcula (nao corrigido por migracao)

-- J. servico_foto com url vazia (fotos "fantasma" gravadas sem arquivo)
SELECT id_foto, id_servico, tipo FROM public.servico_foto WHERE url = '';

-- K. RLS / grants (SEG-12)
SELECT c.relname, c.relrowsecurity AS rls_ativo, c.relforcerowsecurity AS rls_forcado
  FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' ORDER BY 1;
SELECT t.tablename, t.tableowner, r.rolbypassrls
  FROM pg_tables t JOIN pg_roles r ON r.rolname = t.tableowner WHERE t.schemaname = 'public' ORDER BY 1;

-- L. Enum statuschamado (precisa conter os 6 valores de negocio; 'Aberto' e legado e nao pode ser removido facilmente)
SELECT e.enumlabel, e.enumsortorder FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
 WHERE t.typname = 'statuschamado' ORDER BY e.enumsortorder;

-- M. Tipos divergentes do SDD (esperado: ordem_servico.assinatura_cliente_url = varchar(255))
SELECT table_name, column_name, data_type, character_maximum_length
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'ordem_servico' AND column_name = 'assinatura_cliente_url';

-- N. Migracoes controladas (nao ha Alembic nem supabase_migrations aplicadas ate esta rodada)
-- SELECT * FROM supabase_migrations.schema_migrations;   -- (via MCP: list_migrations retornou [])
