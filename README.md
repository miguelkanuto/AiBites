# rag-in-action

RAG simples sobre um CSV de vendas: Chainlit (interface) + LlamaIndex (RAG) + OpenRouter (LLM) + HuggingFace (embeddings locais).

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (baixa o Python 3.13 sozinho)
- Conta no [OpenRouter](https://openrouter.ai) com uma API key
- ~3 GB livres (o `torch` e o modelo de embeddings são pesados)

## Configurar

1. `cp .env.example .env` e preencha `OPENROUTER_API_KEY`.
2. `uv sync`
3. Rodar: `uv run chainlit run src/main.py -w` (ou `make run`). Abre em http://localhost:8000

Na primeira execução o modelo de embeddings é baixado do HuggingFace e o índice é criado em `storage/`. Nas seguintes ele é carregado do disco, e só é refeito se o CSV ou o `EMBED_MODEL` mudarem.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | sim | chave do OpenRouter |
| `OPENROUTER_MODEL` | não | padrão `meta-llama/llama-3.1-8b-instruct` |
| `EMBED_MODEL` | sim | modelo de embeddings do HuggingFace |
| `LOG_LEVEL` | não | padrão `INFO` |
| `HF_TOKEN` | não | evita o aviso de requisições não autenticadas no HF Hub |

## Estrutura

- `src/main.py` — app completo (carga do CSV, índice persistido, query engine, chat)
- `data/sales.csv` — base de vendas
- `storage/` — índice vetorial persistido (gerado)
