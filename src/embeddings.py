"""Embeddings por API (Gemini), sem modelo local.

Tirar o modelo do servidor corta ~480 MB de memória (cabe em planos gratuitos de 512 MB).
Custos desta escolha, que o README também registra:
- cada pergunta depende da API e da cota gratuita do Gemini;
- a chave vai só no cabeçalho `x-goog-api-key`, nunca na URL nem em mensagens de erro;
- vetores com menos de 3072 dimensões precisam de normalização, feita aqui.
"""

import math
import os
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import Field, PrivateAttr

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-embedding-001"
DEFAULT_DIM = 768
BATCH_SIZE = 25  # textos por chamada: lotes menores não estouram a cota de tokens por minuto de uma vez
QUERY_PATIENCE_S = 15.0  # uma pergunta não deve esperar muito por cota
DOCUMENT_PATIENCE_S = 900.0  # a recriação do índice pode esperar a cota por minuto voltar
QUERY_CACHE_SIZE = 256
RETRY_STATUS = {429, 500, 502, 503, 504}

_sleep = time.sleep  # trocável nos testes


class EmbeddingError(RuntimeError):
    """Falha ao gerar embeddings. A mensagem nunca contém a chave da API."""


def normalize(vector: list[float]) -> list[float]:
    """Normaliza o vetor para norma 1 (exigido pelo Gemini abaixo de 3072 dimensões)."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


class GeminiEmbedding(BaseEmbedding):
    """Modelo de embeddings do Gemini compatível com o LlamaIndex."""

    model_name: str = Field(default=DEFAULT_MODEL, description="Modelo (EMBED_MODEL).")
    dim: int = Field(default=DEFAULT_DIM, description="Dimensões do vetor (EMBED_DIM).")
    _api_key: str = PrivateAttr()
    _client: Any = PrivateAttr()
    _cache: "OrderedDict[str, list[float]]" = PrivateAttr()
    _lock: Any = PrivateAttr()

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        dim: int = DEFAULT_DIM,
        api_key: str | None = None,
        client: httpx.Client | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("embed_batch_size", BATCH_SIZE)
        super().__init__(model_name=model_name, dim=dim, **kwargs)
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not key:
            raise EmbeddingError("GEMINI_API_KEY não está definida.")
        self._api_key = key
        self._client = client or httpx.Client(timeout=30.0)
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    @classmethod
    def class_name(cls) -> str:
        return "GeminiEmbedding"

    # --- chamada HTTP -----------------------------------------------------

    def _request(self, task_type: str, texts: list[str], patience: float) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": f"models/{self.model_name}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                    "outputDimensionality": self.dim,
                }
                for text in texts
            ]
        }
        url = f"{API_BASE}/models/{self.model_name}:batchEmbedContents"
        headers = {"x-goog-api-key": self._api_key, "Content-Type": "application/json"}
        deadline = time.monotonic() + patience
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as error:
                # O tipo do erro basta; o texto pode conter a URL da chamada.
                status, detail = None, type(error).__name__
            else:
                status, detail = response.status_code, ""
                if status == 200:
                    return self._parse(response.json(), len(texts))
                if status not in RETRY_STATUS:
                    raise EmbeddingError(f"O provedor de embeddings recusou a chamada (HTTP {status}).")
            wait = min(60.0, 2.0 * 2 ** (attempt - 1))
            if status == 429 and response is not None:
                retry_after = response.headers.get("retry-after", "")
                if retry_after.isdigit():
                    wait = max(wait, float(retry_after))
            if time.monotonic() + wait > deadline:
                motivo = f"HTTP {status}" if status else detail
                raise EmbeddingError(f"Provedor de embeddings indisponível ou sem cota agora ({motivo}).")
            _sleep(wait)

    def _parse(self, data: dict[str, Any], expected: int) -> list[list[float]]:
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != expected:
            raise EmbeddingError("Resposta inesperada do provedor de embeddings.")
        vectors = []
        for item in embeddings:
            values = item.get("values") if isinstance(item, dict) else None
            if not isinstance(values, list) or len(values) != self.dim:
                raise EmbeddingError("Vetor com tamanho inesperado vindo do provedor de embeddings.")
            vectors.append(normalize([float(x) for x in values]))
        return vectors

    # --- interface do LlamaIndex -----------------------------------------

    def _get_query_embedding(self, query: str) -> list[float]:
        with self._lock:
            if query in self._cache:
                self._cache.move_to_end(query)
                return list(self._cache[query])
        vector = self._request("RETRIEVAL_QUERY", [query], QUERY_PATIENCE_S)[0]
        with self._lock:
            self._cache[query] = vector
            while len(self._cache) > QUERY_CACHE_SIZE:
                self._cache.popitem(last=False)
        return list(vector)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        import asyncio

        return await asyncio.to_thread(self._get_query_embedding, query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._request("RETRIEVAL_DOCUMENT", [text], DOCUMENT_PATIENCE_S)[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            out.extend(self._request("RETRIEVAL_DOCUMENT", texts[start : start + BATCH_SIZE], DOCUMENT_PATIENCE_S))
        return out
