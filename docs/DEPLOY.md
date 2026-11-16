# Publicar o site (Render, plano gratuito)

O site (API FastAPI + React compilado) roda numa única imagem Docker. O banco continua no Neon e os
embeddings vêm da API do Gemini (chave gratuita, sem cartão). Não há modelo de embeddings no servidor,
e as ferramentas MCP rodam dentro do mesmo processo (`AIBITES_MCP_MODE=inprocess`), para caber nos
**512 MB** do plano gratuito.

> Estado: o `Dockerfile` **ainda não foi construído** (não há Docker nesta máquina). O primeiro build
> acontece no próprio Render; se falhar, o log mostra o motivo. A memória foi medida localmente no Windows
> **antes** de ligar o modo em memória das ferramentas; depois dele, confira o gráfico de memória do Render.

## O que o plano gratuito do Render tem (conferir na página do Render antes de publicar)

- 512 MB de RAM, CPU fraca e **dorme após 15 minutos parado**: a primeira visita depois disso espera
  de dezenas de segundos a mais de um minuto até o servidor acordar e carregar.
- Segundo uma análise de terceiros, não pede cartão. Confirme no cadastro.

## Passo a passo

1. No Render, entre com a sua conta do GitHub e escolha **New → Web Service**, apontando para o
   repositório do projeto. **Runtime: Docker. Instance type: Free.**
2. Em **Environment**, cadastre como variáveis (nunca no código):

   | Nome | Valor |
   |---|---|
   | `OPENROUTER_API_KEY` | sua chave do OpenRouter |
   | `OPENROUTER_MODEL`, `OPENROUTER_MODEL_LIGHT`, `OPENROUTER_MODEL_STRONG` | os mesmos do seu `.env` |
   | `GEMINI_API_KEY` | sua chave do Google AI Studio |
   | `AIBITES_DATABASE_URL` | URL do banco com o usuário `aibites_app` (menor privilégio) |
   | `CHAINLIT_AUTH_SECRET` | texto aleatório longo |
   | `SITE_SESSION_SECRET` | outro texto aleatório longo |
   | `MCP_CONTEXT_SECRET` | outro texto aleatório longo |

   **Não** cadastre `AIBITES_ADMIN_DATABASE_URL`: o servidor público não deve ter a credencial do dono do
   banco. Sem ela o app só lê o índice (o índice é gerenciado por `db/build_index.py`, rodado no seu computador).
3. Em **Health Check Path**, use `/api/health`.
4. Faça o deploy e abra o endereço `*.onrender.com`. `/api/health` deve trazer `"pronto": true` depois da carga.

## Atualizar o índice (no seu computador, com a credencial de dono no `.env`)

```bash
uv run python db/build_index.py
```

Isso apaga e recria a tabela de vetores com o Gemini (alguns minutos por causa do limite por minuto da API).
Rode depois de mudar dados ou o modelo de embeddings.

## Limites conhecidos (dizer na entrevista)

- **Dependência de API:** cada pergunta chama o Gemini para gerar o vetor (o cache de consultas repetidas
  reduz isso). Se a cota gratuita acabar, o assistente avisa que a busca está indisponível em vez de inventar
  uma resposta. Os limites exatos da cota gratuita não foram confirmados na página oficial.
- Os modelos do OpenRouter também são gratuitos e têm limite diário.
- O login do site é por persona fictícia, sem senha. Os limites por visitante existem, mas qualquer pessoa
  pode usar o site.
- As ferramentas MCP rodam no mesmo processo do servidor neste modo (sem isolamento de processo); o
  contexto assinado e a política de acesso continuam valendo. Uma ferramenta lenta pode atrasar as outras.
- As sessões ficam em memória: reiniciar ou acordar o servidor encerra as sessões abertas.
- Os "bancos" de RH, TI e Slack são arquivos locais efêmeros e fictícios.
- Sem o manifesto local do índice, a versão usada pelo cache semântico fica vazia no servidor público:
  o cache não é invalidado sozinho quando os dados mudam (limpe `cache_semantico` ao recriar o índice).
