-- Esquema do banco de vendas (PostgreSQL).
-- A tabela de vetores (data_sales_rag) é criada sozinha pelo LlamaIndex/pgvector.

CREATE TABLE IF NOT EXISTS produtos (
    produto_id      TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    marca           TEXT NOT NULL,
    descricao       TEXT NOT NULL,
    preco_unitario  NUMERIC(10, 2) NOT NULL CHECK (preco_unitario > 0),
    estoque         INTEGER NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    ativo           BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS vendedores (
    vendedor_id     TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    regiao          TEXT NOT NULL,
    cargo           TEXT NOT NULL,
    data_admissao   DATE NOT NULL,
    meta_mensal     NUMERIC(12, 2) NOT NULL CHECK (meta_mensal > 0)
);

CREATE TABLE IF NOT EXISTS vendas (
    venda_id        INTEGER PRIMARY KEY,
    data_venda      DATE NOT NULL,
    produto_id      TEXT NOT NULL REFERENCES produtos (produto_id),
    vendedor_id     TEXT NOT NULL REFERENCES vendedores (vendedor_id),
    quantidade      INTEGER NOT NULL CHECK (quantidade > 0),
    preco_unitario  NUMERIC(10, 2) NOT NULL CHECK (preco_unitario > 0),
    valor_total     NUMERIC(12, 2) NOT NULL CHECK (valor_total > 0),
    forma_pagamento TEXT NOT NULL,
    status          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vendas_produto ON vendas (produto_id);
CREATE INDEX IF NOT EXISTS idx_vendas_vendedor ON vendas (vendedor_id);
CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas (data_venda);
