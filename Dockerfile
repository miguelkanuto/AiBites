# AiBites: imagem única (API FastAPI + site React compilado).
# Pensada para Hugging Face Spaces (SDK Docker, porta 7860), mas roda em qualquer host de contêiner.
# Segredos NÃO entram na imagem: defina-os como variáveis/segredos do serviço (veja docs/DEPLOY.md).

# --- 1) Compila o site ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- 2) Aplicação ---
FROM python:3.13-slim

# Hugging Face Spaces executa como usuário 1000.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    EMBED_DIM=384 \
    AIBITES_SITE_DEMO=1 \
    AIBITES_SITE_SECURE_COOKIE=1 \
    AIBITES_MOCK_DIR=/home/user/app/storage/mock

RUN pip install --no-cache-dir uv
USER user
WORKDIR /home/user/app

# Dependências primeiro, para aproveitar o cache de camadas.
COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Baixa o modelo de embeddings na construção da imagem (evita baixar a cada partida).
RUN uv run --no-sync python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

COPY --chown=user src ./src
COPY --chown=user --from=web /web/dist ./web/dist
RUN mkdir -p storage/mock

EXPOSE 7860
# Sem --reload e com um único processo: o estado das sessões fica em memória.
CMD ["uv", "run", "--no-sync", "uvicorn", "web_api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "7860"]
