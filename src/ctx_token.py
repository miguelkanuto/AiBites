"""Contexto de usuário assinado, para o servidor de ferramentas saber quem pede.

O modelo de linguagem nunca vê este contexto nem escolhe a identidade: o app
(host) assina quem está logado e o injeta em toda chamada de ferramenta. O
servidor confere a assinatura e a validade antes de qualquer coisa, então um
argumento forjado pelo modelo ("sou a Helena") não vira identidade.
"""

import base64
import hashlib
import hmac
import json
import os
import time

from rbac import Usuario

MAX_AGE_SECONDS = 120


class ContextoInvalido(Exception):
    """Contexto ausente, adulterado ou vencido."""


def _secret() -> bytes:
    explicit = os.getenv("MCP_CONTEXT_SECRET")
    if explicit:
        return explicit.encode("utf-8")

    base = os.getenv("CHAINLIT_AUTH_SECRET")
    if not base:
        raise ContextoInvalido("Defina MCP_CONTEXT_SECRET ou CHAINLIT_AUTH_SECRET.")
    # Chave derivada: o segredo de sessão do Chainlit não é usado diretamente aqui.
    return hmac.new(base.encode("utf-8"), b"aibites-mcp-context", hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(usuario: Usuario, now: float | None = None) -> str:
    """Assina o contexto do usuário logado (válido por `MAX_AGE_SECONDS`)."""
    payload = json.dumps(
        {**usuario.to_metadata(), "t": now if now is not None else time.time()},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(signature)}"


def verify(token: str, now: float | None = None) -> Usuario:
    """Confere assinatura e validade e devolve o usuário.

    Raises:
        ContextoInvalido: Quando o token está vazio, malformado, adulterado ou vencido.
    """
    if not token or token.count(".") != 1:
        raise ContextoInvalido("Contexto ausente ou malformado.")

    try:
        payload_b64, signature_b64 = token.split(".")
        payload = _unb64(payload_b64)
        signature = _unb64(signature_b64)
    except (ValueError, TypeError) as error:
        raise ContextoInvalido("Contexto malformado.") from error

    expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ContextoInvalido("Assinatura do contexto inválida.")

    try:
        data = json.loads(payload)
        issued = float(data.pop("t"))
        usuario = Usuario.from_metadata(data)
    except (ValueError, KeyError, TypeError) as error:
        raise ContextoInvalido("Conteúdo do contexto inválido.") from error

    current = now if now is not None else time.time()
    if not -5 <= current - issued <= MAX_AGE_SECONDS:
        raise ContextoInvalido("Contexto vencido.")

    return usuario
