# AiBites: imagem única (API FastAPI + site React compilado).
# Pensada para o plano gratuito do Render (512 MB), mas roda em qualquer host de contêiner.
# Segredos NÃO entram na imagem: defina-os como variáveis de ambiente do serviço (veja docs/DEPLOY.md).

# --- 1) Compila o site ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- 2) Aplicação ---
FROM python:3.13-slim

RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:/home/user/.local/bin:$PATH \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    EMBED_MODEL=gemini-embedding-001 \
    EMBED_DIM=768 \
    AIBITES_SITE_DEMO=1 \
    AIBITES_SITE_SECURE_COOKIE=1 \
    AIBITES_MCP_MODE=inprocess \
    AIBITES_MOCK_DIR=/home/user/app/storage/mock

RUN pip install --no-cache-dir uv
USER user
WORKDIR /home/user/app

# Dependências primeiro, para aproveitar o cache de camadas.
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user src ./src
COPY --chown=user --from=web /web/dist ./web/dist
RUN mkdir -p storage/mock

EXPOSE 10000
# Um único processo (as sessões ficam em memória) e sem o `uv` como processo pai, para poupar RAM.
# O Render define PORT; fora dele, usa 10000.
CMD ["sh", "-c", "exec uvicorn web_api:app --app-dir src --host 0.0.0.0 --port ${PORT:-10000}"]
