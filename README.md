# AiBites: assistente corporativo com RAG e agente (projeto de demonstração)

A **Carol** é a assistente da AiBites, uma empresa fictícia. Ela responde perguntas sobre produtos, vendedores e vendas (RAG sobre PostgreSQL/pgvector) e, como **agente**, executa ações por ferramentas: pedir férias, abrir ticket de TI, mandar mensagem num canal e calcular totais e rankings de vendas. Tudo respeita o login e o papel de quem pergunta.

> Os dados e os sistemas externos (RH, TI, Slack) são **fictícios e simulados**. Os modelos de linguagem são reais e gratuitos (OpenRouter); o custo exibido é **simulado** com preços de referência.

Stack: Chainlit (interface) · LlamaIndex (RAG) · PostgreSQL + pgvector (dados e vetores) · MCP (ferramentas) · OpenRouter (LLM) · embeddings locais em ONNX (fastembed, modelo MiniLM multilíngue).

## Como uma mensagem é tratada

```
mensagem → limites e risco → guardrails (regras + juiz leve na zona cinzenta) → roteador
   ├─ conversa fiada ........ resposta pronta (sem modelo, custo zero)
   ├─ consulta à base ....... cache semântico → RAG com RBAC no banco → modelo padrão
   └─ ação ou conta exata ... agente → ferramentas MCP (política + confirmação) → modelo forte
→ filtro de saída (prompt vazado, dados pessoais) → resposta → auditoria por usuário
```

## Site de demonstração

Um site (FastAPI + React) para mostrar o projeto a quem for avaliá-lo, com quatro áreas:

- **Demonstração:** escolha uma persona (cliente, vendedor, gerente, RH, TI ou CEO) e converse com a Carol. Há perguntas sugeridas, confirmação das ações dentro do chat e um **inspetor** que mostra, a cada resposta, a rota, o modelo, a latência, o custo simulado, o cache, os guardrails, os documentos e as ferramentas usados.
- **Laboratório:** microssimulações sem custo, que rodam as mesmas funções do assistente: guardrails (pontuação e redação de dados pessoais), roteador com comparação de custo por faixa, matriz de permissões e o cache semântico seguro.
- **Como foi feito:** o caminho de uma mensagem em diagrama (os blocos acendem conforme a última mensagem enviada), as decisões de projeto, a stack e o que é simulado.
- **Métricas:** números agregados da auditoria dos últimos 7 dias (rotas, cache, economia do roteamento, ferramentas e bloqueios), sem dados pessoais.

```
make site        # compila o React e serve em http://localhost:8001
```

Para desenvolver: `make api` (API na 8001) e `make web` (Vite na 5173, com proxy para a API). O chat do Chainlit (`make run`) e o site usam o **mesmo pipeline** (`src/pipeline.py`), então RBAC, guardrails, roteador, cache, agente e auditoria valem igual nos dois.

O site não pede senha: quem visita escolhe uma persona fictícia (`AIBITES_SITE_DEMO=1`; use `0` para desligar). Cada visitante recebe um id próprio, então limites e auditoria não se misturam. O cookie é assinado e `HttpOnly`; defina `AIBITES_SITE_SECURE_COOKIE=1` atrás de HTTPS. As sessões ficam em memória (uma instância) e expiram em 2 horas.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (baixa o Python 3.13 sozinho)
- Conta no [OpenRouter](https://openrouter.ai) com uma API key (os modelos `:free` têm limite diário)
- Um PostgreSQL com a extensão `vector`. O plano gratuito do [Neon](https://neon.tech) serve.
- ~3 GB livres (o `torch` e o modelo de embeddings são pesados)

## Configurar

1. `cp .env.example .env`; preencha `OPENROUTER_API_KEY` e coloque em `AIBITES_DATABASE_URL` a URL do **dono** do banco por enquanto. Gere o `CHAINLIT_AUTH_SECRET` com `uv run chainlit create-secret`.
2. `uv sync`
3. Criar as tabelas e os dados fictícios: `uv run python db/seed.py`
4. Criar o usuário de menor privilégio do app: `uv run python db/setup_roles.py`. Ele cria o usuário `aibites_app`, passa a URL do dono para `AIBITES_ADMIN_DATABASE_URL` e grava a do app em `AIBITES_DATABASE_URL` (a senha é gerada e não é impressa).
5. Rodar: `uv run chainlit run src/main.py -w` (ou `make run`). Abre em http://localhost:8000. O servidor abre em ~12 s; modelo e índice carregam em segundo plano (~40 s), e a primeira conversa espera isso.

Depois de mudar dados, regras de acesso ou o modelo de embeddings, o índice é refeito sozinho **se** `AIBITES_ADMIN_DATABASE_URL` estiver definida; em produção, omita-a e rode `uv run python db/build_index.py`.

## Login e permissões (RBAC)

O acesso exige login. As contas são **fictícias** (tabela `usuarios`) e todas usam a senha `demo123`:

| E-mail | Papel | O que a Carol pode mostrar |
| --- | --- | --- |
| `paulo.mendes@mendes-informatica.com.br` | cliente | só produtos; sem ferramentas |
| `carlos.lima@loja-exemplo.com.br` / `rafael.martins@loja-exemplo.com.br` | vendedor | produtos, vendedores, as próprias vendas e o próprio salário |
| `rodrigo.campos@loja-exemplo.com.br` | TI | produtos, vendedores, o próprio salário e a fila de chamados |
| `marcos.teixeira@loja-exemplo.com.br` | gerente de vendas | acima, mais as vendas de todos e o ranking de vendedores |
| `juliana.prado@loja-exemplo.com.br` | RH | produtos, vendedores e salários (menos o do CEO) |
| `helena.vasconcelos@loja-exemplo.com.br` | CEO | tudo, inclusive o próprio salário |

A permissão é aplicada **na consulta ao banco**, antes de qualquer texto chegar ao modelo (cada documento tem `nivel` e `dono`), com segunda checagem no código (`src/rbac.py`). Não depende do prompt.

## Agente e ferramentas (MCP)

Quatro servidores MCP, cada um num processo próprio (`src/mcp_servers/`):

| Servidor | Ferramentas | Observações |
| --- | --- | --- |
| `rh` | `consultar_saldo_ferias`, `listar_solicitacoes_ferias`, `solicitar_ferias` | 30 dias por ano de casa, máximo de 60 (regra fictícia); valida datas, saldo e sobreposição |
| `ti` | `abrir_ticket`, `consultar_ticket`, `listar_meus_tickets`, `listar_fila` | não duplica um chamado igual aberto nos últimos 10 min; só dono, TI e CEO veem o chamado |
| `slack` | `listar_canais`, `enviar_mensagem` | canais por papel (`#diretoria` só do CEO); dados pessoais redigidos |
| `vendas` | `total_vendido`, `total_por_categoria`, `ranking_vendedores` | contas exatas em SQL parametrizado, só leitura; contam vendas concluídas; é o "submodelo de matemática" |

Regras de segurança do agente (`src/agent.py`, `src/tool_policy.py`, `src/ctx_token.py`):

- O modelo só **vê** as ferramentas que o papel do usuário pode usar.
- Qualquer chamada fora da política é barrada no app **e** de novo no servidor.
- Ferramentas que alteram algo (férias, ticket, mensagem) pedem **confirmação** na tela, com botões, e há no máximo 2 por mensagem.
- Quem está pedindo vem de um **contexto assinado** (HMAC, validade de 2 min) injetado pelo app. O modelo nunca escolhe a identidade nem vê esse campo.
- Cada chamada é gravada em `tool_calls` (argumentos já redigidos) e aparece como um passo na conversa.

Os bancos dos sistemas fictícios (RH, TI, Slack) ficam em SQLite, em `storage/mock/` (ou em `AIBITES_MOCK_DIR`).

## Roteador, cache e custo (simulado)

| Rota | Quando | Modelo | Custo |
| --- | --- | --- | --- |
| conversa fiada | "oi", "obrigado", "tchau" | resposta pronta | zero |
| consulta | catálogo, vendedores, vendas, salários | faixa padrão | baixo |
| agente | férias, tickets, mensagens, somas, rankings | faixa forte | alto |

O **cache semântico** (`cache_semantico`, pgvector) reaproveita respostas de perguntas parecidas (similaridade ≥ 0,92, validade de 24 h). Para não vazar nada, só guarda respostas montadas com documentos que o papel enxerga **pelo nível**, a chave inclui os níveis do papel, perguntas na primeira pessoa ("meu salário") não entram e ele perde a validade se os dados mudarem. Cada resposta registra rota, modelo, latência e custo simulado em `log_conversas`.

## Proteções

- **Login:** 5 senhas erradas em 5 min bloqueiam o e-mail (e há um limite global contra quem troca de e-mail a cada tentativa). Os contadores vêm das tabelas de auditoria, então valem entre reinícios e instâncias.
- **Mensagens:** 10 por minuto e 300 por dia por usuário, até 1000 caracteres.
- **Injeção de prompt:** regras em português e inglês, com normalização de acentos, caixa, caracteres invisíveis e "leetspeak" (`src/guardrails.py`). Na zona cinzenta (suspeita, mas sem bloqueio), um modelo leve dá um segundo parecer (`src/judge.py`).
- **Pontuação de risco por usuário:** mensagens suspeitas somam pontos; passando de 120 em 1 hora, o usuário fica pausado até a soma cair.
- **Dados pessoais:** CPF, CNPJ, cartão (com dígito verificador) e telefone são redigidos antes do modelo, nas respostas e nos logs; e-mails também nos logs.
- **Prompt de sistema:** respostas que repetem trechos dele são trocadas por uma recusa.
- **Auditoria:** `log_conversas` (por usuário), `tool_calls` e `eventos_seguranca`. O usuário do app só **insere** nessas tabelas: não edita nem apaga.
- **Banco:** o app usa o usuário `aibites_app` (lê o negócio, insere nos logs, escreve no cache); o dono do banco só aparece para seed e recriação do índice.
- **Configuração:** sessão de 8 horas, CORS restrito a `localhost:8000`, upload de arquivos desligado.

## Testes

```
uv run pytest tests -q
```

Os testes unitários (política, senhas, guardrails, roteador, agente com modelo falso, cache, custo) rodam sem banco. Os de integração usam o PostgreSQL do `.env`, os servidores MCP reais (com bancos temporários) e o modelo de embeddings, e levam alguns minutos. **Nenhum teste chama o LLM**; testes pulados não contam como aprovados.

## Variáveis de ambiente

Veja `.env.example`. Não use o nome `DATABASE_URL`: o Chainlit o reconhece sozinho e tenta guardar o histórico de conversas nesse banco, o que causa "Internal Server Error".

## Estrutura

- `src/main.py`: app Chainlit (RAG, índice, login)
- `src/pipeline.py`: fluxo de uma mensagem, compartilhado entre o Chainlit e a API do site
- `src/web_api.py`, `src/personas.py`, `web/`: API do site (FastAPI) e front-end (React + TypeScript)
- `src/rbac.py`, `src/auth.py`: permissões e senhas
- `src/guardrails.py`, `src/judge.py`, `src/limits.py`, `src/audit.py`: proteções e auditoria
- `src/router.py`, `src/llm.py`, `src/cache.py`: roteador, faixas de modelo e cache
- `src/agent.py`, `src/mcp_hub.py`, `src/tool_policy.py`, `src/ctx_token.py`, `src/mcp_servers/`: agente e ferramentas
- `db/schema.sql`, `db/seed.py`, `db/setup_roles.py`, `db/build_index.py`: banco
- `public/`, `.chainlit/config.toml`: identidade visual e configuração
- `tests/`: testes

## Limites conhecidos

- Integrações e dados são simulados; não há conexão com RH, Jira ou Slack reais.
- Guardrails por regras e um juiz de modelo pequeno reduzem o risco, mas não o eliminam. Quem protege os dados é o RBAC no banco e a política de ferramentas.
- O agente pode acrescentar detalhes que o resultado da ferramenta não trouxe; o prompt pede para não fazer isso, mas isso não é garantido.
- O bloqueio de login pode deixar um usuário legítimo de fora por alguns minutos.
- Modelos gratuitos têm limite diário e de provedor; o agente usa mais chamadas que o RAG.
- O login do Chainlit é compartilhado entre portas do `localhost` (mesmo cookie), o que importa ao testar várias instâncias.
- O site usa login de demonstração sem senha; só serve para uma demonstração pública com dados fictícios. Os limites por visitante dependem do id da sessão, que é criado a cada visita.
- As métricas do site contam só respostas que registram o custo de referência (as mais antigas não entram na economia).
- Ainda não há o "pergunte sobre a arquitetura" no site, a suíte de avaliação com bloqueio de release, o Docker nem o login com Google.

## Publicar o site

Veja [docs/DEPLOY.md](docs/DEPLOY.md): imagem Docker única (`Dockerfile`) pensada para Hugging Face Spaces, com o banco no Neon.
