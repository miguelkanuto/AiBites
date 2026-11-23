# AiBites · Carol

Assistente corporativo com **RAG**, **agente com ferramentas (MCP)**, **controle de acesso por papel** e **guardrails**, feito como projeto de demonstração. A Carol atende a AiBites, uma loja fictícia: responde sobre produtos, vendedores e vendas, e executa ações (pedir férias, abrir ticket de TI, mandar mensagem no Slack, calcular totais e rankings) respeitando quem está perguntando.

**Demonstração:** https://aibites.onrender.com (plano gratuito: a primeira visita pode demorar para o servidor acordar)

> Dados, RH, TI e Slack são **fictícios e simulados**. Os modelos de linguagem são reais e gratuitos (OpenRouter); o custo exibido é **simulado** com preços de referência.

## O que o projeto mostra

- **RAG com permissão no banco:** o filtro de acesso (RBAC) roda na consulta, antes de qualquer texto chegar ao modelo.
- **Agente com ferramentas MCP:** RH, TI, Slack e vendas (SQL parametrizado, só leitura), com política por papel, confirmação das ações e identidade assinada.
- **Roteador de modelos:** conversa fiada sem modelo, consulta na faixa padrão, ações e contas exatas na faixa forte.
- **Cache semântico seguro** no pgvector e custo simulado por faixa.
- **Proteções:** injeção de prompt (regras + juiz leve), redação de dados pessoais, limites e pontuação de risco por usuário, auditoria.
- **Qualidade:** testes unitários e de integração, suíte de avaliação com gate de release e CI.
- **Site de demonstração** (FastAPI + React) com inspetor de cada resposta, laboratório de microssimulações, diagrama da arquitetura e métricas.

Stack: FastAPI · React + TypeScript · Chainlit · LlamaIndex · PostgreSQL + pgvector (Neon) · MCP · OpenRouter · embeddings `gemini-embedding-001` (768 dimensões).

## Como uma mensagem é tratada

```
mensagem → limites e risco → guardrails (regras + juiz leve na zona cinzenta) → roteador
   ├─ conversa fiada ........ resposta pronta (sem modelo, custo zero)
   ├─ consulta à base ....... cache semântico → RAG com RBAC no banco → modelo padrão
   └─ ação ou conta exata ... agente → ferramentas MCP (política + confirmação) → modelo forte
→ filtro de saída (prompt vazado, dados pessoais) → resposta → auditoria por usuário
```

O fluxo fica em `src/pipeline.py` e é compartilhado pelo site e pelo Chainlit: as regras de segurança valem igual nos dois.

## Site de demonstração

| Área | O que tem |
| --- | --- |
| Demonstração | Escolha uma persona (cliente, vendedor, gerente, RH, TI ou CEO) e converse. O **inspetor** mostra rota, modelo, latência, custo simulado, cache, guardrails, documentos e ferramentas de cada resposta. |
| Laboratório | Microssimulações sem custo que rodam as mesmas funções do assistente: guardrails, roteador, matriz de permissões e cache semântico. |
| Arquitetura | O caminho da mensagem em diagrama, decisões de projeto e o que é simulado. |
| Métricas | Agregados da auditoria dos últimos 7 dias, sem dados pessoais. |

O site não pede senha: o visitante escolhe uma persona fictícia (`AIBITES_SITE_DEMO=1`; `0` desliga). Cada visitante recebe um id próprio, então limites e auditoria não se misturam. O cookie é assinado e `HttpOnly`; use `AIBITES_SITE_SECURE_COOKIE=1` atrás de HTTPS.

## Começando

Pré-requisitos: [uv](https://docs.astral.sh/uv/) (baixa o Python 3.13), uma chave do [OpenRouter](https://openrouter.ai), um PostgreSQL com a extensão `vector` ([Neon](https://neon.tech) gratuito serve) e uma chave gratuita do Google AI Studio (`GEMINI_API_KEY`) para os embeddings.

```bash
cp .env.example .env          # preencha OPENROUTER_API_KEY, GEMINI_API_KEY e AIBITES_DATABASE_URL (do dono, por enquanto)
uv sync
uv run python db/seed.py         # tabelas e dados fictícios
uv run python db/setup_roles.py  # usuário de menor privilégio do app
make site                        # compila o React e serve em http://localhost:8001
```

Chat do Chainlit: `make run` (http://localhost:8000). Desenvolvimento do site: `make api` (porta 8001) e `make web` (Vite na 5173).

Depois de mudar dados, regras de acesso ou o modelo de embeddings, refaça o índice com `uv run python db/build_index.py` (usa uma chamada de embedding por documento e consome a cota gratuita do Gemini). Veja `.env.example` para as variáveis. Não use o nome `DATABASE_URL`: o Chainlit o reconhece e tenta guardar o histórico nele.

## Permissões (RBAC)

A permissão é aplicada **na consulta ao banco** (cada documento tem `nivel` e `dono`), com segunda checagem em `src/rbac.py`. Não depende do prompt.

| Persona | O que a Carol pode mostrar |
| --- | --- |
| Cliente | Só produtos; sem ferramentas |
| Vendedor | Produtos, vendedores, as próprias vendas e o próprio salário |
| TI | Produtos, vendedores, o próprio salário e a fila de chamados |
| Gerente de vendas | O do vendedor, mais as vendas de todos e o ranking |
| RH | Produtos, vendedores e salários (menos o do CEO) |
| CEO | Tudo |

No Chainlit o login usa e-mail e senha das contas fictícias de `db/seed.py` (a senha de demonstração é `demo123`).

## Agente e ferramentas (MCP)

| Servidor | Ferramentas |
| --- | --- |
| `rh` | saldo de férias, solicitações, solicitar férias |
| `ti` | abrir, consultar e listar tickets, fila de chamados |
| `slack` | listar canais, enviar mensagem (canais por papel) |
| `vendas` | total vendido, total por categoria, ranking de vendedores (SQL só leitura) |

- O modelo só **vê** as ferramentas que o papel pode usar; uma chamada fora da política é barrada no app **e** no servidor.
- Ações que alteram algo pedem **confirmação** na tela (no máximo 2 por mensagem).
- A identidade vem de um **contexto assinado** (HMAC, validade de 2 min), nunca escolhida pelo modelo.
- Cada chamada é gravada em `tool_calls`, com argumentos redigidos.
- Modos de execução: processos separados (`AIBITES_MCP_MODE=stdio`, padrão) ou em memória (`inprocess`, usado no deploy gratuito por economia de memória).

Os "sistemas" de RH, TI e Slack são SQLite em `storage/mock/` (ou `AIBITES_MOCK_DIR`).

## Proteções

- **Login e mensagens:** bloqueio por tentativas, 10 mensagens por minuto e 300 por dia por usuário.
- **Injeção de prompt:** regras em português e inglês (acentos, caixa, caracteres invisíveis, leetspeak) e um juiz leve na zona cinzenta.
- **Risco por usuário:** mensagens suspeitas somam pontos; passando de 120 em 1 hora, o usuário é pausado.
- **Dados pessoais:** CPF, CNPJ, cartão e telefone são redigidos antes do modelo, nas respostas e nos logs.
- **Prompt de sistema:** respostas que o repetem são trocadas por uma recusa.
- **Auditoria:** `log_conversas`, `tool_calls` e `eventos_seguranca`; o usuário do app só insere, não edita nem apaga.
- **Banco:** o app usa `aibites_app` (menor privilégio); a credencial de dono só aparece para seed e recriação do índice e **não deve ir para o servidor público**.

## Testes e avaliação

```bash
uv run pytest tests -q                         # unitários e de integração (integração precisa do .env e leva alguns minutos)
uv run pytest tests -q -m "not integration"    # o que roda no CI, sem segredos
make eval URL=http://localhost:8001            # avaliação com casos reais contra um site em execução
```

Nenhum teste chama o LLM. A avaliação (`evals/`) chama o modelo de verdade, recusa toda confirmação (nada é criado) e falha se uma categoria ficar abaixo do limiar; segurança e RBAC exigem 100%. Detalhes e medidas de otimização em [docs/AVALIACAO.md](docs/AVALIACAO.md).

## Publicação

Imagem Docker única (`Dockerfile`) para o plano gratuito do Render, com o banco no Neon e embeddings no Gemini; `render.yaml` cria o serviço. Passo a passo, limites e como mudar o endereço em [docs/DEPLOY.md](docs/DEPLOY.md).

## Versionamento

[SemVer](https://semver.org/lang/pt-BR/) (`MAIOR.MENOR.CORREÇÃO`), com a versão no rodapé do site e em `/api/health`. A página recarrega sozinha quando sai uma versão ou deploy novo. Histórico em [CHANGELOG.md](CHANGELOG.md).

## Estrutura

```
src/        pipeline, API do site, roteador, agente, MCP, guardrails, RBAC, cache, embeddings
web/        site (React + TypeScript + Vite)
db/         schema, seed, usuário de menor privilégio, índice vetorial
evals/      casos e executor da avaliação
tests/      testes
docs/       deploy e avaliação
```

## Limites conhecidos

- Integrações e dados são simulados; não há conexão com RH, Jira ou Slack reais.
- Guardrails reduzem o risco, mas não o eliminam. Quem protege os dados é o RBAC no banco e a política de ferramentas.
- O site usa login de demonstração sem senha, adequado só para dados fictícios; as sessões ficam em memória e se perdem ao reiniciar.
- Cada pergunta depende da API de embeddings e dos modelos gratuitos, que têm limite diário; se a cota acabar, o assistente avisa em vez de inventar uma resposta.
- Perguntas de contagem que caem no RAG podem ser imprecisas; contas exatas vão para o agente com SQL.
- O agente pode acrescentar detalhes que a ferramenta não trouxe; o prompt pede para não fazer isso, mas não é garantido.
- Não há login com Google.
