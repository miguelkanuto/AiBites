# rag-in-action

RAG sobre uma base de vendas em PostgreSQL: Chainlit (interface) + LlamaIndex (RAG) + PostgreSQL com pgvector (dados e vetores) + OpenRouter (LLM) + HuggingFace (embeddings locais).

As 3 tabelas (`produtos`, `vendedores`, `vendas`) viram documentos, os vetores ficam na tabela `data_sales_rag` do mesmo banco, e o chat responde perguntas do tipo "qual" e "quais". Perguntas de soma e ranking não são função do RAG (ficam para uma etapa com SQL).

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (baixa o Python 3.13 sozinho)
- Conta no [OpenRouter](https://openrouter.ai) com uma API key
- Um PostgreSQL com a extensão `vector` (pgvector). O plano gratuito do [Neon](https://neon.tech) serve.
- ~3 GB livres (o `torch` e o modelo de embeddings são pesados)

## Configurar

1. `cp .env.example .env` e preencha `OPENROUTER_API_KEY` e `DATABASE_URL`.
2. `uv sync`
3. Criar as tabelas e popular o banco: `uv run python db/seed.py`
4. Rodar: `uv run chainlit run src/main.py -w` (ou `make run`). Abre em http://localhost:8000

A busca é **híbrida** (vetores + palavra-chave em português, no próprio PostgreSQL) e cada linha das tabelas é indexada como uma frase. Isso evita confundir, por exemplo, "Norte" com "Nordeste".

Na primeira execução o modelo de embeddings é baixado do HuggingFace e o índice é criado no PostgreSQL. Nas seguintes ele é carregado do banco, e só é refeito se os dados das tabelas ou o `EMBED_MODEL` mudarem.

## Login e permissões (RBAC)

O acesso exige login. As contas são **fictícias** (tabela `usuarios`, criada pelo `db/seed.py`) e todas usam a senha `demo123`:

| E-mail | Papel | O que a Carol pode mostrar |
| --- | --- | --- |
| `paulo.mendes@mendes-informatica.com.br` | cliente | só produtos |
| `carlos.lima@loja-exemplo.com.br` / `rafael.martins@loja-exemplo.com.br` | vendedor | produtos, vendedores, as próprias vendas e o próprio salário |
| `rodrigo.campos@loja-exemplo.com.br` | TI | produtos, vendedores e o próprio salário |
| `marcos.teixeira@loja-exemplo.com.br` | gerente de vendas | acima, mais as vendas de todos |
| `juliana.prado@loja-exemplo.com.br` | RH | produtos, vendedores e salários (menos o do CEO) |
| `helena.vasconcelos@loja-exemplo.com.br` | CEO | tudo, inclusive o próprio salário |

A permissão é aplicada **na consulta ao banco**, antes de qualquer texto chegar ao modelo (cada documento tem `nivel` e `dono`), com uma segunda checagem no código. Não depende do prompt. A política está em `src/rbac.py`.

Gere o segredo de sessão do Chainlit com `uv run chainlit create-secret` e coloque em `CHAINLIT_AUTH_SECRET` no `.env`.

## Testes

```
uv run pytest tests -q
```

Os testes unitários (política e senhas) rodam sem banco. Os de integração usam o PostgreSQL do `.env` e o modelo de embeddings (levam alguns minutos) e **não chamam o LLM**.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | sim | chave do OpenRouter |
| `OPENROUTER_MODEL` | não | padrão `meta-llama/llama-3.1-8b-instruct` |
| `DATABASE_URL` | sim | string de conexão do PostgreSQL (`postgresql://...?sslmode=require`) |
| `CHAINLIT_AUTH_SECRET` | sim | segredo de sessão do login (`uv run chainlit create-secret`) |
| `EMBED_MODEL` | sim | modelo de embeddings do HuggingFace |
| `EMBED_DIM` | não | dimensão do embedding, padrão `384` (o do modelo acima) |
| `LOG_LEVEL` | não | padrão `INFO` |
| `HF_TOKEN` | não | evita o aviso de requisições não autenticadas no HF Hub |

## Estrutura

- `src/main.py` — app completo (leitura do banco, índice, query engine, chat)
- `public/` — identidade visual da AiBites: `theme.json` (cores azul-marinho, claro e escuro), `custom.css` (barra de rolagem), logos, favicon e avatar
- `.chainlit/config.toml` — nome do app (AiBites), tema padrão e CSS
- `src/rbac.py` — política de acesso por papel; `src/auth.py` — hash de senhas
- `tests/` — testes da política, do login e da busca por papel
- `db/schema.sql` — tabelas `produtos`, `vendedores`, `vendas`, `funcionarios`, `clientes` e `usuarios`
- `db/seed.py` — aplica o schema e popula 40 produtos, 10 vendedores e 500 vendas (dados fictícios, sempre iguais)
- `data/sales.csv` — CSV original do curso (não é mais usado pelo app)
- `storage/index_metadata.json` — hash dos dados e modelo usados no índice (gerado)
