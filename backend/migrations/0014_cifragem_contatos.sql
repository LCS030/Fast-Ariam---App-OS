-- =============================================================================
-- 0014_cifragem_contatos.sql  --  prepara o banco para mais campos pessoais CIFRADOS pela aplicacao (v0.7, H2;
--                                  AES-256-GCM, prefixo "enc1:", mesmo mecanismo da 0011)
--
--   * cliente.contato_principal_nome, cliente.contato_principal_telefone  e  visita.nome_cliente_assinatura  ->  TEXT
--     (o texto cifrado e bem maior que o valor original; varchar(100)/varchar(20) nao comporta)
--   * NAO ha CHECK nem UNIQUE nem indice nessas colunas (nada a remover); nenhuma consulta do backend filtra/ordena por elas
--   * cliente.telefone (comercial, PJ) NAO e alterado: continua em claro (decisao do PO, D5 reescrita)
--   * sync_evento.payload (JSONB) NAO precisa de DDL: as chaves `documento_cliente` e `nome_cliente` passam a guardar
--     strings "enc1:..." dentro do proprio JSONB (H1, somente codigo; pode ir ao ar sem esta migracao)
--   * visita.nome_ajudante / telefone_ajudante (H3) ficam FORA: so entram se a contagem de 0014_consultas_conferencia.sql
--     mostrar dado real; ver o bloco comentado ao final
--
-- NAO CIFRA OS DADOS: isso e feito por scripts/cifrar_dados_existentes.py (idempotente, prefixo "enc1:"). Ordem OBRIGATORIA:
--   1) backup (scripts/backup_banco.py)   2) esta migracao   3) scripts/cifrar_dados_existentes.py
--   4) scripts/cifrar_dados_existentes.py --verificar (somente leitura; sai com codigo != 0 se houver pendencia)
--      + consultas de 0014_consultas_conferencia.sql (todas devem dar 0)
-- Compativel com o backend ANTIGO enquanto nao houver valor cifrado: varchar -> text nao perde dado nem rejeita escrita.
-- ATENCAO: depois do script, o backend ANTIGO (sem a cifragem v0.7) passa a ler "enc1:..." como se fosse o valor real.
-- Dev e producao compartilham o mesmo projeto Supabase. Rollback: 0014_rollback.sql (exige antes:
--   python scripts/cifrar_dados_existentes.py --decifrar; o rollback ABORTA se restar qualquer "enc1:").
-- O backup do passo 1 contem contato, nome e CPF em claro e sem cifra: trate como dado pessoal (fora do repositorio,
-- acesso restrito, descarte definido apos a validacao).
-- =============================================================================
BEGIN;

SET LOCAL lock_timeout = '10s';

DO $mig$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('cliente', 'contato_principal_nome'),
      ('cliente', 'contato_principal_telefone'),
      ('visita',  'nome_cliente_assinatura')
    ) AS v(tabela, coluna)
  LOOP
    IF to_regclass('public.' || r.tabela) IS NULL THEN
      RAISE EXCEPTION 'Tabela public.% nao existe: schema base ausente. Abortando.', r.tabela;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = r.tabela AND column_name = r.coluna) THEN
      RAISE EXCEPTION 'Coluna public.%.% nao existe: schema base divergente. Abortando.', r.tabela, r.coluna;
    END IF;
  END LOOP;
END
$mig$;

-- varchar -> text e uma conversao binaria-compativel (sem reescrita da tabela); idempotente se a coluna ja for text.
ALTER TABLE public.cliente
  ALTER COLUMN contato_principal_nome     TYPE text,
  ALTER COLUMN contato_principal_telefone TYPE text;

ALTER TABLE public.visita ALTER COLUMN nome_cliente_assinatura TYPE text;

-- -----------------------------------------------------------------------------
-- H3 (CONDICIONAL, desativado): so descomente se a contagem agregada de 0014_consultas_conferencia.sql (secao H3) mostrar
-- linhas nao nulas em visita.nome_ajudante / telefone_ajudante E o PO confirmar a inclusao. Se 0 linhas: nao altere
-- (colunas legadas vazias, RN-25). Se descomentar aqui, inclua o mesmo no 0014_rollback.sql (travas e varchar de volta).
-- -----------------------------------------------------------------------------
-- ALTER TABLE public.visita
--   ALTER COLUMN nome_ajudante     TYPE text,
--   ALTER COLUMN telefone_ajudante TYPE text;

COMMIT;
