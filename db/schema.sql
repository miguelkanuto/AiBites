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

-- Dados de RH: acesso restrito (ver src/rbac.py).
CREATE TABLE IF NOT EXISTS funcionarios (
    funcionario_id  TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    cargo           TEXT NOT NULL,
    departamento    TEXT NOT NULL,
    salario         NUMERIC(12, 2) NOT NULL CHECK (salario > 0),
    data_admissao   DATE NOT NULL,
    gerente_id      TEXT REFERENCES funcionarios (funcionario_id),
    vendedor_id     TEXT UNIQUE REFERENCES vendedores (vendedor_id)
);

CREATE TABLE IF NOT EXISTS clientes (
    cliente_id      TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    empresa         TEXT NOT NULL
);

-- Contas de login (fictícias). Funcionário e cliente são mutuamente exclusivos.
CREATE TABLE IF NOT EXISTS usuarios (
    usuario_id      TEXT PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    nome            TEXT NOT NULL,
    papel           TEXT NOT NULL
                    CHECK (papel IN ('cliente', 'vendedor', 'ti', 'gerente_vendas', 'rh', 'ceo')),
    funcionario_id  TEXT REFERENCES funcionarios (funcionario_id),
    cliente_id      TEXT REFERENCES clientes (cliente_id),
    senha_hash      TEXT NOT NULL,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (
        (papel = 'cliente' AND cliente_id IS NOT NULL AND funcionario_id IS NULL)
        OR (papel <> 'cliente' AND funcionario_id IS NOT NULL AND cliente_id IS NULL)
    )
);

-- Auditoria: uma linha por pergunta, com dados pessoais já redigidos.
-- Sem chave estrangeira em usuario_id, para o histórico sobreviver à remoção da conta.
CREATE TABLE IF NOT EXISTS log_conversas (
    log_id          BIGSERIAL PRIMARY KEY,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    usuario_id      TEXT NOT NULL,
    papel           TEXT NOT NULL,
    sessao_id       TEXT,
    pergunta        TEXT NOT NULL,
    resposta        TEXT,
    bloqueada       BOOLEAN NOT NULL DEFAULT FALSE,
    motivos         TEXT[] NOT NULL DEFAULT '{}',
    risco           INTEGER NOT NULL DEFAULT 0,
    documentos      TEXT[] NOT NULL DEFAULT '{}',
    latencia_ms     INTEGER,
    modelo          TEXT
);

ALTER TABLE log_conversas ADD COLUMN IF NOT EXISTS trace_id TEXT;
ALTER TABLE log_conversas ADD COLUMN IF NOT EXISTS rota TEXT;
ALTER TABLE log_conversas ADD COLUMN IF NOT EXISTS custo_simulado NUMERIC(12, 6);
ALTER TABLE log_conversas ADD COLUMN IF NOT EXISTS custo_referencia NUMERIC(12, 6);

CREATE INDEX IF NOT EXISTS idx_log_conversas_usuario ON log_conversas (usuario_id, criado_em DESC);

-- Rastro de cada chamada de ferramenta do agente (argumentos já redigidos).
CREATE TABLE IF NOT EXISTS tool_calls (
    call_id         BIGSERIAL PRIMARY KEY,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id        TEXT NOT NULL,
    usuario_id      TEXT NOT NULL,
    papel           TEXT NOT NULL,
    servidor        TEXT NOT NULL,
    ferramenta      TEXT NOT NULL,
    argumentos      JSONB,
    status          TEXT NOT NULL,
    resultado       TEXT,
    duracao_ms      INTEGER,
    confirmada      BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_usuario ON tool_calls (usuario_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_trace ON tool_calls (trace_id);

-- Eventos de segurança: login falho, conta bloqueada, limite excedido, usuário pausado.
CREATE TABLE IF NOT EXISTS eventos_seguranca (
    evento_id       BIGSERIAL PRIMARY KEY,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo            TEXT NOT NULL,
    usuario         TEXT,
    detalhe         TEXT
);

CREATE INDEX IF NOT EXISTS idx_eventos_seguranca_tipo ON eventos_seguranca (tipo, criado_em DESC);

-- Cache semântico das respostas do RAG (ver src/cache.py). Dimensão 384 = modelo de embeddings.
CREATE TABLE IF NOT EXISTS cache_semantico (
    cache_id        BIGSERIAL PRIMARY KEY,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em       TIMESTAMPTZ NOT NULL,
    escopo          TEXT NOT NULL,
    versao_indice   TEXT NOT NULL,
    pergunta        TEXT NOT NULL,
    embedding       vector(384) NOT NULL,
    resposta        TEXT NOT NULL,
    acertos         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cache_semantico_escopo ON cache_semantico (escopo, versao_indice);

CREATE INDEX IF NOT EXISTS idx_vendas_produto ON vendas (produto_id);
CREATE INDEX IF NOT EXISTS idx_vendas_vendedor ON vendas (vendedor_id);
CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas (data_venda);
