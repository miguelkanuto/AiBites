# AGENTS.md

Projeto `rag-in-action`: chat com Chainlit + LlamaIndex usando OpenRouter, com dados em PostgreSQL (tabelas `produtos`, `vendedores`, `vendas`) e índice vetorial no pgvector (tabela `data_sales_rag`).

## Comandos
- Instalar: `uv sync`
- Popular o banco: `uv run python db/seed.py`
- Rodar: `make run` (`uv run chainlit run src/main.py -w`)

## Convenções
- Código do app em `src/main.py`; SQL e seed em `db/`; Python 3.13 e gerenciador `uv`.
- Variáveis de ambiente em `.env` (modelo em `.env.example`); nunca commitar `.env` nem a `DATABASE_URL`.
- Respostas e prompts em português do Brasil.
- O índice é refeito sozinho quando os dados do banco ou o `EMBED_MODEL` mudam.
