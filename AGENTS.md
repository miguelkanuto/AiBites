# AGENTS.md

Projeto `rag-in-action` (AiBites / Carol): chat com Chainlit + LlamaIndex, dados em PostgreSQL (pgvector), agente com ferramentas MCP e RBAC por papel. Veja o README para a arquitetura.

## Comandos
- Instalar: `uv sync`
- Popular o banco (como dono): `uv run python db/seed.py`
- Criar o usuário de menor privilégio: `uv run python db/setup_roles.py`
- Recriar o índice vetorial (como dono): `uv run python db/build_index.py`
- Rodar o chat: `make run` (`uv run chainlit run src/main.py -w`)
- Rodar o site: `make site` (compila `web/` e serve em http://localhost:8001); desenvolvimento: `make api` e `make web`
- Testes: `uv run pytest tests -q` (os de integração precisam do `.env` e levam alguns minutos)

## Convenções
- App em `src/` (módulos pequenos por assunto); SQL e seeds em `db/`; Python 3.13 e gerenciador `uv`.
- Variáveis em `.env` (modelo em `.env.example`); nunca commitar `.env`, URLs de banco nem chaves.
- Nunca nomear a variável do banco `DATABASE_URL` (o Chainlit a usa como banco de histórico).
- Permissão se aplica no servidor (consulta ao banco, política de ferramentas, servidores MCP), nunca só no prompt.
- Ferramentas que alteram algo exigem confirmação do usuário e passam por `tool_policy.py`.
- O fluxo da mensagem fica em `src/pipeline.py`; Chainlit e API do site só fornecem usuário, estado e hooks. Não duplicar regras de segurança nas interfaces.
- Em comandos de shell que geram código com `\b` ou `\d`, escreva o arquivo com a ferramenta de edição: barras invertidas duplicadas se perdem.
- Toda regra de segurança nova vem com teste; o LLM não é chamado nos testes.
- Respostas e prompts em português do Brasil.
