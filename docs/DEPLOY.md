# Publicar o site (Hugging Face Spaces)

O site (API FastAPI + React compilado) roda numa única imagem Docker. O banco continua no Neon.
Escolhi o Hugging Face Spaces porque o servidor usa cerca de **1,3 GB de RAM** (medido localmente,
com o modelo de embeddings carregado), mais do que cabe em planos gratuitos de 512 MB.
Os limites atuais do plano gratuito devem ser conferidos na página do Hugging Face antes de publicar.

> Estado: o `Dockerfile` **ainda não foi construído** (não há Docker nesta máquina). O primeiro build
> acontece no próprio Space; se falhar, o log de build mostra o motivo.

## Passo a passo

1. Crie uma conta em huggingface.co e um **Space** novo: SDK **Docker**, template em branco, visibilidade pública.
2. Em **Settings → Variables and secrets** do Space, cadastre como **Secrets** (nunca no código):

   | Nome | Valor |
   |---|---|
   | `OPENROUTER_API_KEY` | sua chave do OpenRouter |
   | `AIBITES_DATABASE_URL` | URL do banco com o usuário `aibites_app` (menor privilégio) |
   | `CHAINLIT_AUTH_SECRET` | texto aleatório longo |
   | `SITE_SESSION_SECRET` | outro texto aleatório longo |
   | `MCP_CONTEXT_SECRET` | outro texto aleatório longo |
   | `OPENROUTER_MODEL`, `OPENROUTER_MODEL_LIGHT`, `OPENROUTER_MODEL_STRONG` | os mesmos do seu `.env` |

   **Não** cadastre `AIBITES_ADMIN_DATABASE_URL`: o servidor público não deve ter a credencial do dono do banco.
3. Envie o código ao Space. O Space exige um `README.md` com cabeçalho próprio, diferente do README do GitHub.
   Use o modelo `docs/hf-space-README.md` numa branch separada:

   ```bash
   git remote add space https://huggingface.co/spaces/SEU_USUARIO/NOME_DO_SPACE
   git checkout -b hf
   cp docs/hf-space-README.md README.md
   git add README.md && git commit -m "chore(deploy): README do Space"
   git push space hf:main
   git checkout master
   ```
4. Aguarde o build. Abra o endereço **`https://SEU_USUARIO-NOME_DO_SPACE.hf.space`** (não a página
   `huggingface.co/spaces/...`): o cookie de sessão do site precisa de uma página de nível superior.
5. Teste `/api/health`: a resposta deve trazer `"pronto": true` depois de cerca de 40 s.

## Limites conhecidos (dizer na entrevista)

- O Space gratuito **dorme** quando fica parado; a primeira visita depois disso espera a partida.
- Os modelos do OpenRouter são gratuitos e têm limite diário: se acabar, as respostas falham até o dia seguinte.
- O login do site é por persona fictícia, sem senha. Os limites por visitante existem, mas qualquer pessoa pode usar o site.
- As sessões ficam em memória: reiniciar o Space encerra as sessões abertas.
- Os "bancos" de RH, TI e Slack são arquivos locais efêmeros e fictícios.
