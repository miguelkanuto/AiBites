"""Falha do provedor de embeddings: o pipeline avisa em vez de responder sem consultar a base."""

import asyncio

import pytest

import pipeline
from embeddings import EmbeddingError


class _Modelo:
    def __init__(self, erro: Exception | None = None):
        self._erro = erro

    def get_query_embedding(self, texto: str) -> list[float]:
        if self._erro:
            raise self._erro
        return [0.1, 0.2, 0.3]


class _Core:
    def __init__(self, erro: Exception | None = None):
        self._modelo = _Modelo(erro)

    def create_embed_model(self) -> _Modelo:
        return self._modelo


def test_devolve_o_vetor_quando_o_provedor_responde() -> None:
    assert asyncio.run(pipeline.embed_query(_Core(), "oi")) == [0.1, 0.2, 0.3]


def test_provedor_sem_cota_vira_none_e_nao_derruba_a_mensagem() -> None:
    erro = EmbeddingError("Provedor de embeddings indisponível ou sem cota agora (HTTP 429).")
    assert asyncio.run(pipeline.embed_query(_Core(erro), "oi")) is None


def test_erro_de_programacao_nao_e_engolido() -> None:
    with pytest.raises(ZeroDivisionError):
        asyncio.run(pipeline.embed_query(_Core(ZeroDivisionError()), "oi"))


def test_a_mensagem_de_indisponibilidade_nao_inventa_resposta() -> None:
    assert "indisponível" in pipeline.MSG_EMBEDDINGS_DOWN
    assert "tente de novo" in pipeline.MSG_EMBEDDINGS_DOWN.lower()
