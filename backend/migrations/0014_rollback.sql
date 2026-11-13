-- =============================================================================
-- 0014_rollback.sql  --  desfaz 0014_cifragem_contatos.sql
-- PRE-REQUISITO: rodar `python scripts/cifrar_dados_existentes.py --decifrar` (volta os valores para texto puro, inclusive
-- as chaves cifradas de sync_evento.payload). Sem isso a migracao ABORTA: estreitar as colunas com texto cifrado dentro
-- corromperia/recusaria os dados. O rollback NAO depende de restauracao de backup (a restauracao nunca foi testada, SEG-28).
-- SEQUENCIA OBRIGATORIA: 1) PARAR a API (nenhuma instancia pode escrever); 2) python scripts/cifrar_dados_existentes.py
-- --decifrar; 3) esta migracao; 4) subir o codigo anterior. NAO mantenha o backend v0.7 no ar durante o --decifrar: depois
-- dele o v0.7 le texto puro em coluna cifrada e responde 500 (ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false), e qualquer escrita
-- do v0.7 recifra o valor e a trava abaixo aborta.
-- Nota: o sync_evento.payload (JSONB) nao tem DDL na 0014; so o --decifrar o desfaz. Esta trava tambem verifica o payload
-- (chaves documento_cliente / nome_cliente) para nao deixar "enc1:" para tras.
-- A trava usa LIKE 'enc1:%': pode dar FALSO POSITIVO com linha anomala (texto legitimo que comece com "enc1:"). Isso e
-- intencional: abortar e o lado seguro; investigue a linha (so contagem/ID, sem expor o valor) antes de seguir.
-- =============================================================================
BEGIN;
SET LOCAL lock_timeout = '10s';

DO $mig$
BEGIN
  IF EXISTS (SELECT 1 FROM public.cliente
              WHERE contato_principal_nome LIKE 'enc1:%' OR contato_principal_telefone LIKE 'enc1:%')
     OR EXISTS (SELECT 1 FROM public.visita WHERE nome_cliente_assinatura LIKE 'enc1:%')
     OR EXISTS (SELECT 1 FROM public.sync_evento
                 WHERE payload ->> 'documento_cliente' LIKE 'enc1:%' OR payload ->> 'nome_cliente' LIKE 'enc1:%') THEN
    RAISE EXCEPTION 'Ainda ha valores cifrados (enc1:). Rode scripts/cifrar_dados_existentes.py --decifrar antes. Abortando.';
  END IF;

  -- Seguranca extra: valores gravados enquanto a coluna era TEXT podem exceder o limite antigo; falhar aqui, com mensagem
  -- clara, em vez de deixar o ALTER ... TYPE varchar(n) abortar com erro generico.
  IF EXISTS (SELECT 1 FROM public.cliente
              WHERE char_length(contato_principal_nome) > 100 OR char_length(contato_principal_telefone) > 20)
     OR EXISTS (SELECT 1 FROM public.visita WHERE char_length(nome_cliente_assinatura) > 100) THEN
    RAISE EXCEPTION 'Ha valores maiores que o limite antigo (varchar 100/20). Revise os dados antes de estreitar. Abortando.';
  END IF;
END
$mig$;

ALTER TABLE public.cliente
  ALTER COLUMN contato_principal_nome     TYPE varchar(100),
  ALTER COLUMN contato_principal_telefone TYPE varchar(20);

ALTER TABLE public.visita ALTER COLUMN nome_cliente_assinatura TYPE varchar(100);

-- H3 (se tiver sido ativado na 0014): restaurar tambem visita.nome_ajudante varchar(100) e telefone_ajudante varchar(20),
-- com a mesma trava de 'enc1:' e de tamanho acima.

COMMIT;
