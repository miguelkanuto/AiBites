"""Quando um modelo gratuito falha, a chamada tenta os outros em vez de derrubar a mensagem."""

import asyncio
from types import SimpleNamespace

import pytest

import llm


def _resposta(texto: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=texto, tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


class _Cliente:
    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.modelos: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.modelos.append(kwargs["model"])
        resultado = self.respostas[kwargs["model"]]
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL_LIGHT", "leve")
    monkeypatch.setenv("OPENROUTER_MODEL", "padrao")
    monkeypatch.setenv("OPENROUTER_MODEL_STRONG", "forte")

    def instalar(respostas):
        cliente = _Cliente(respostas)
        monkeypatch.setattr(llm, "get_client", lambda: cliente)
        return cliente

    return instalar


def test_corpo_sem_choices_cai_para_o_proximo_modelo(ambiente):
    cliente = ambiente({"padrao": SimpleNamespace(choices=None, usage=None), "leve": _resposta("ok do leve"), "forte": _resposta("x")})
    resultado = asyncio.run(llm.chat("standard", [{"role": "user", "content": "oi"}]))
    assert resultado.text == "ok do leve"
    assert cliente.modelos[0] == "padrao"
    assert resultado.tier.name == "standard"


def test_todos_falhando_levanta_provider_unavailable(ambiente):
    vazio = SimpleNamespace(choices=[], usage=None)
    ambiente({"padrao": vazio, "leve": vazio, "forte": vazio})
    with pytest.raises(llm.ProviderUnavailable):
        asyncio.run(llm.chat("standard", [{"role": "user", "content": "oi"}]))


def test_sem_falha_usa_so_o_modelo_da_faixa(ambiente):
    cliente = ambiente({"padrao": _resposta("direto"), "leve": _resposta("x"), "forte": _resposta("x")})
    resultado = asyncio.run(llm.chat("standard", [{"role": "user", "content": "oi"}]))
    assert resultado.text == "direto"
    assert cliente.modelos == ["padrao"]
