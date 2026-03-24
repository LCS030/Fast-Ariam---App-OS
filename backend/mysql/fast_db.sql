/* Script SQL Completo - Fast Ariam API v1 */
CREATE DATABASE IF NOT EXISTS fast DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE fast;

/* --- Tabela de Técnicos (e Admins) --- */
CREATE TABLE IF NOT EXISTS tecnico (
    id_tecnico INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(100) NOT NULL,
    cpf VARCHAR(14) NOT NULL UNIQUE,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    inscricao_estadual VARCHAR(50),
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(20),
    password_hash VARCHAR(100) NOT NULL,
    role ENUM('admin', 'tecnico') NOT NULL DEFAULT 'tecnico',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    dados_bancarios JSON /* Armazena: {banco, agencia, conta, pix} */
);

/* --- Tabela de Clientes --- */
CREATE TABLE IF NOT EXISTS cliente (
    id_cliente INT PRIMARY KEY AUTO_INCREMENT,
    razao_social VARCHAR(100) NOT NULL,
    codigo INT UNIQUE NOT NULL, /* Código legado da Fast */
    contato_principal_nome VARCHAR(100) NOT NULL,
    contato_principal_telefone VARCHAR(20) NOT NULL,
    telefone VARCHAR(20) NOT NULL,
    endereco VARCHAR(200) NOT NULL,
    numero VARCHAR(20) NOT NULL,
    bairro VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    uf VARCHAR(2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

/* --- Tabela de Chamados (Ordem de Serviço) --- */
CREATE TABLE IF NOT EXISTS ordem_servico (
    id_os INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL,
    id_tecnico_atribuido INT,
    
    status VARCHAR(50) NOT NULL DEFAULT 'Aberto', /* "Aberto", "Agendado", "Em Atendimento", "Pendente", "Finalizado" */
    is_cancelled BOOLEAN NOT NULL DEFAULT FALSE,
    
    data_abertura DATE NOT NULL,
    data_agendamento DATE,
    data_conclusao DATE,
    
    descricao_cliente TEXT,
    pedido VARCHAR(100),
    data_faturamento DATE,
    em_garantia BOOLEAN NOT NULL DEFAULT TRUE,
    
    FOREIGN KEY (id_cliente) REFERENCES cliente(id_cliente),
    FOREIGN KEY (id_tecnico_atribuido) REFERENCES tecnico(id_tecnico)
);

/* --- Tabela de Visitas (Viagens) --- */
CREATE TABLE IF NOT EXISTS visita (
    id_visita INT PRIMARY KEY AUTO_INCREMENT,
    id_os INT NOT NULL,
    
    data_visita DATE NOT NULL,
    hora_inicio_deslocamento VARCHAR(5),
    hora_chegada_cliente VARCHAR(5),
    hora_inicio_atendimento VARCHAR(5),
    hora_fim_atendimento VARCHAR(5),
    
    km_total INT NOT NULL DEFAULT 0,
    valor_pedagio DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    valor_frete_devolucao DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    
    descricao_servico_executado TEXT,
    nome_ajudante VARCHAR(100),
    telefone_ajudante VARCHAR(20),
    
    servico_finalizado BOOLEAN NOT NULL DEFAULT FALSE,
    pendencia TEXT,
    
    /* Campos de Upload de Arquivos */
    odometro_inicio_url VARCHAR(255),
    odometro_fim_url VARCHAR(255),
    assinatura_cliente_url VARCHAR(255),
    comprovante_pedagio_urls JSON NOT NULL DEFAULT (JSON_ARRAY()), /* Armazena uma LISTA de URLs: ["/url1.jpg", "/url2.jpg"] */
    comprovante_frete_urls JSON NOT NULL DEFAULT (JSON_ARRAY()),   /* Armazena uma LISTA de URLs */
    
    FOREIGN KEY (id_os) REFERENCES ordem_servico(id_os) ON DELETE CASCADE /* Se apagar a OS, apaga as visitas */
);

/* --- Tabela de Serviços por Equipamento (O trabalho feito) --- */
CREATE TABLE IF NOT EXISTS servico_equipamento (
    id_servico INT PRIMARY KEY AUTO_INCREMENT,
    id_visita INT NOT NULL,
    
    numero_serie_atendido VARCHAR(100) NOT NULL,
    
    /* Armazena as listas de Enums como JSON */
    defeitos_principais JSON, /* Ex: ["Refrigeração", "Iluminação"] */
    defeito_outros_descricao TEXT,
    sub_defeitos_refrigeracao JSON,
    sub_defeitos_compressor JSON,
    sub_defeitos_vazamento JSON,
    vazamento_ponto_descricao TEXT,
    sub_defeitos_outros JSON,
    sub_defeitos_iluminacao JSON,
    sub_defeitos_estrutura JSON,
    
    FOREIGN KEY (id_visita) REFERENCES visita(id_visita) ON DELETE CASCADE
);

/* --- Tabela de Materiais Utilizados --- */
/* Esta tabela está ligada ao servico_equipamento, não à visita */
CREATE TABLE IF NOT EXISTS material (
    id_material INT PRIMARY KEY AUTO_INCREMENT,
    id_servico INT NOT NULL, /* Chave estrangeira para o serviço/equipamento específico */
    
    nome VARCHAR(100) NOT NULL,
    quantidade INT NOT NULL,
    valor DECIMAL(10, 2) NOT NULL,
    
    FOREIGN KEY (id_servico) REFERENCES servico_equipamento(id_servico) ON DELETE CASCADE
);