"""Camada de modelos: níveis (leve, padrão, forte) com preço simulado e cliente OpenRouter.

Os modelos são reais e gratuitos no OpenRouter, mas o custo é **simulado** com
preços de referência de cada faixa (US$ por 1 milhão de tokens), para mostrar o
efeito do roteamento sem gastar nada. Cada nível pode ser trocado por variável de ambiente.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, BadRequestError, InternalServerError, RateLimitError

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ProviderUnavailable(RuntimeError):
    """Nenhum modelo gratuito respondeu agora (limite, fila ou erro do provedor)."""

# Modelos que recusam `reasoning: disabled` (descobertos na primeira chamada).
_REASONING_REQUIRED: set[str] = set()


@dataclass(frozen=True)
class Tier:
    """Faixa de modelo.

    Attributes:
        name: `light`, `standard` ou `strong`.
        model: Id do modelo no OpenRouter.
        input_price: Preço simulado de entrada, US$ por 1M de tokens.
        output_price: Preço simulado de saída, US$ por 1M de tokens.
    """

    name: str
    model: str
    input_price: float
    output_price: float


def get_tiers() -> dict[str, Tier]:
    """Monta as três faixas a partir do ambiente (lido a cada chamada)."""
    return {
        "light": Tier(
            "light",
            os.getenv("OPENROUTER_MODEL_LIGHT", "liquid/lfm-3-1.7b:free"),
            input_price=0.05,
            output_price=0.10,
        ),
        "standard": Tier(
            "standard",
            os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free"),
            input_price=0.30,
            output_price=0.90,
        ),
        "strong": Tier(
            "strong",
            os.getenv("OPENROUTER_MODEL_STRONG", "nvidia/nemotron-3-ultra-550b-a55b:free"),
            input_price=3.00,
            output_price=15.00,
        ),
    }


def estimate_cost(tier: Tier, prompt_tokens: int, completion_tokens: int) -> float:
    """Custo simulado (US$) de uma chamada, pelos preços de referência da faixa."""
    return (prompt_tokens * tier.input_price + completion_tokens * tier.output_price) / 1_000_000


def reference_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Custo simulado se a mesma chamada tivesse ido sempre para a faixa forte."""
    return estimate_cost(get_tiers()["strong"], prompt_tokens, completion_tokens)


@dataclass
class ChatResult:
    """Resposta de uma chamada de chat.

    Attributes:
        message: Mensagem do assistente (texto e/ou `tool_calls`).
        tier: Faixa usada.
        prompt_tokens: Tokens de entrada.
        completion_tokens: Tokens de saída.
        cost: Custo simulado em US$.
    """

    message: Any
    tier: Tier
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    raw: Any = field(default=None, repr=False)

    @property
    def text(self) -> str:
        """Texto da resposta (vazio se o modelo só pediu ferramentas)."""
        return (self.message.content or "").strip()


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    """Cliente assíncrono compatível com a API da OpenAI, apontando para o OpenRouter."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("A variável de ambiente OPENROUTER_API_KEY não foi configurada.")
    # Falha rápida: quem refaz a tentativa em outro modelo é `chat` (modelos gratuitos têm picos de fila de
    # dezenas de segundos; esperar 60 s três vezes no mesmo modelo era o pior caso medido).
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, max_retries=1, timeout=30)


async def chat(
    tier_name: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 512,
    temperature: float = 0.1,
    json_mode: bool = False,
) -> ChatResult:
    """Faz uma chamada de chat na faixa escolhida.

    Args:
        tier_name: `light`, `standard` ou `strong`.
        messages: Mensagens no formato da API (`role` e `content`).
        tools: Ferramentas no formato da API (opcional).
        max_tokens: Limite de tokens da resposta.
        temperature: Temperatura de amostragem.
        json_mode: Pede resposta em JSON (quando o modelo suporta).

    Returns:
        `ChatResult` com a mensagem, os tokens e o custo simulado.
    """
    tier = get_tiers()[tier_name]
    arguments: dict[str, Any] = {
        "model": tier.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        arguments["tools"] = tools
    if json_mode:
        arguments["response_format"] = {"type": "json_object"}

    def with_reasoning(required: bool) -> dict[str, Any]:
        # Quando dá, o raciocínio fica desligado: nos modelos gratuitos ele consome
        # os tokens da resposta. Alguns modelos o exigem; aí ele fica no mínimo e o
        # limite de tokens sobe para sobrar espaço para a resposta.
        reasoning = {"effort": "low"} if required else {"enabled": False}
        extra = {"provider": {"sort": "latency"}, "reasoning": reasoning}
        return {**arguments, "extra_body": extra, **({"max_tokens": max(max_tokens, 1200)} if required else {})}

    async def call(model: str) -> Any:
        arguments["model"] = model
        required = model in _REASONING_REQUIRED
        try:
            response = await get_client().chat.completions.create(**with_reasoning(required))
        except BadRequestError as error:
            if required or "mandatory" not in str(error).lower():
                raise
            _REASONING_REQUIRED.add(model)
            response = await get_client().chat.completions.create(**with_reasoning(True))
        if not getattr(response, "choices", None):
            # O OpenRouter às vezes devolve HTTP 200 com um erro do provedor no corpo.
            raise ProviderUnavailable(f"Sem resposta do modelo {model}.")
        return response

    # Modelos gratuitos falham de vez em quando (limite, fila, erro do provedor): tenta os outros da lista.
    tiers = get_tiers()
    candidates = list(dict.fromkeys([tier.model, tiers["standard"].model, tiers["strong"].model, tiers["light"].model]))
    last_error: Exception | None = None
    response = None
    for model in candidates:
        started = time.perf_counter()
        try:
            response = await call(model)
            logger.info("LLM %s respondeu em %.1fs", model, time.perf_counter() - started)
            break
        except (ProviderUnavailable, RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as error:
            logger.warning("LLM %s falhou em %.1fs (%s)", model, time.perf_counter() - started, type(error).__name__)
            last_error = error
    if response is None:
        raise ProviderUnavailable("Nenhum modelo respondeu agora.") from last_error
    usage = response.usage
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    return ChatResult(
        message=response.choices[0].message,
        tier=tier,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=estimate_cost(tier, prompt_tokens, completion_tokens),
        raw=response,
    )
