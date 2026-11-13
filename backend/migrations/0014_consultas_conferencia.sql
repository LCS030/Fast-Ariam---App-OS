-- =============================================================================
-- 0014_consultas_conferencia.sql  --  consultas SOMENTE LEITURA (SELECT count) para a janela da v0.7
-- ESCRITAS, NAO EXECUTADAS pelo agente DBA. Execute no SQL Editor do Supabase (ou psql), uma de cada vez.
-- Nenhuma consulta devolve valor pessoal: so contagens. Nao copie resultados com dado pessoal para relatorios.
--
-- Secao T: tipos das colunas (rodar ANTES da 0014 = "antes"; e DEPOIS da 0014, antes do script = tem de ser text)
-- Secao A: rodar ANTES (linha de base; antes da 0014 as colunas ainda sao varchar; todas as consultas funcionam)
-- Secao B: rodar DEPOIS do script + --verificar: as 3 consultas devem dar 0 (B3 so olha o prefixo 'enc1:', entao vale
--          para qualquer AAD/versao de contexto)
-- Secao C: contagem agregada de H3 (decide se visita.nome_ajudante/telefone_ajudante entram); rodar ANTES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- T. TIPOS DAS COLUNAS (information_schema) -- GATE da janela: prova que a 0014 foi (ou nao) aplicada.
--    O `--dry-run` do script NAO acusa estouro de varchar, entao esta consulta e o gate.
--    T-antes (ANTES da 0014): esperado varchar com limite (cliente 100/20, visita 100) -- anote o resultado.
--    T-depois (DEPOIS da 0014, antes do script): as 3 linhas devem ter data_type = 'text'. Qualquer outra coisa: NAO rodar o script.
-- -----------------------------------------------------------------------------
SELECT table_name, column_name, data_type, character_maximum_length
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND ((table_name = 'cliente' AND column_name IN ('contato_principal_nome', 'contato_principal_telefone'))
     OR (table_name = 'visita'  AND column_name = 'nome_cliente_assinatura'))
 ORDER BY table_name, column_name;

-- T-depois, versao booleana: deve retornar tipos_text = 3 e falhas = 0 (esperado: 3 colunas, todas text).
SELECT count(*) FILTER (WHERE data_type = 'text')  AS tipos_text,
       count(*) FILTER (WHERE data_type <> 'text') AS falhas
  FROM information_schema.columns
 WHERE table_schema = 'public'
   AND ((table_name = 'cliente' AND column_name IN ('contato_principal_nome', 'contato_principal_telefone'))
     OR (table_name = 'visita'  AND column_name = 'nome_cliente_assinatura'));

-- -----------------------------------------------------------------------------
-- A. LINHA DE BASE (antes) -- quanto o script deve cifrar; compare com o resumo do `--dry-run`
-- -----------------------------------------------------------------------------
SELECT
  (SELECT count(*) FROM public.cliente WHERE contato_principal_nome     IS NOT NULL) AS cliente_contato_nome_nao_nulos,
  (SELECT count(*) FROM public.cliente WHERE contato_principal_telefone IS NOT NULL) AS cliente_contato_tel_nao_nulos,
  (SELECT count(*) FROM public.visita  WHERE nome_cliente_assinatura    IS NOT NULL) AS visita_nome_assinatura_nao_nulos,
  (SELECT count(*) FROM public.sync_evento
    WHERE payload ? 'documento_cliente' OR payload ? 'nome_cliente')                  AS sync_evento_com_chave_pessoal;

-- -----------------------------------------------------------------------------
-- B. CONFERENCIA (depois) -- as TRES consultas abaixo devem retornar 0
-- -----------------------------------------------------------------------------
-- B1. cliente: contato ainda em claro (nao nulo e sem o prefixo enc1:)
SELECT count(*) AS cliente_contato_em_claro
  FROM public.cliente
 WHERE (contato_principal_nome     IS NOT NULL AND contato_principal_nome     NOT LIKE 'enc1:%')
    OR (contato_principal_telefone IS NOT NULL AND contato_principal_telefone NOT LIKE 'enc1:%');

-- B2. visita: nome de quem assinou ainda em claro
SELECT count(*) AS visita_nome_assinatura_em_claro
  FROM public.visita
 WHERE nome_cliente_assinatura IS NOT NULL AND nome_cliente_assinatura NOT LIKE 'enc1:%';

-- B3. sync_evento: CPF/nome no payload (aplicado E rejeitado, qualquer tipo) ainda legiveis.
--     Pendencia = chave presente, com valor diferente de JSON null, que nao seja string "enc1:...".
--     (valor JSON null fica null por decisao do PO; valor nao-string tambem tem de estar cifrado)
SELECT count(*) AS sync_evento_payload_em_claro
  FROM public.sync_evento
 WHERE (payload ? 'documento_cliente' AND jsonb_typeof(payload -> 'documento_cliente') <> 'null'
        AND (jsonb_typeof(payload -> 'documento_cliente') <> 'string'
             OR (payload ->> 'documento_cliente') NOT LIKE 'enc1:%'))
    OR (payload ? 'nome_cliente' AND jsonb_typeof(payload -> 'nome_cliente') <> 'null'
        AND (jsonb_typeof(payload -> 'nome_cliente') <> 'string'
             OR (payload ->> 'nome_cliente') NOT LIKE 'enc1:%'));

-- -----------------------------------------------------------------------------
-- C. H3 -- contagem agregada das colunas legadas de ajudante (sem ler valores)
--    0 em todas as colunas => NAO alterar; registrar "colunas legadas vazias" (RN-25).
-- -----------------------------------------------------------------------------
SELECT
  count(*)                                                       AS visitas_total,
  count(nome_ajudante)                                           AS nome_ajudante_nao_nulos,
  count(*) FILTER (WHERE btrim(nome_ajudante) <> '')             AS nome_ajudante_nao_vazios,
  count(telefone_ajudante)                                       AS telefone_ajudante_nao_nulos,
  count(*) FILTER (WHERE btrim(telefone_ajudante) <> '')         AS telefone_ajudante_nao_vazios
  FROM public.visita;
