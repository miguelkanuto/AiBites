"""Registro de auditoria: conversas por usuário e eventos de segurança.

Tudo o que é gravado passa por `redact` antes, então CPF, cartão, telefone e
e-mail digitados nunca chegam ao banco. Falha ao gravar o log não derruba o chat.
"""

import logging
from collections.abc import Sequence

from guardrails import redact
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

MAX_LOGGED_CHARS = 4000


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return redact(value)[:MAX_LOGGED_CHARS]


def _redact_values(value):
    """Redige dados pessoais em cada texto de uma estrutura, mantendo o JSON válido."""
    if isinstance(value, str):
        return redact(value)[:MAX_LOGGED_CHARS]
    if isinstance(value, dict):
        return {key: _redact_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_values(item) for item in value]
    return value


def log_conversation(
    engine: Engine,
    *,
    usuario_id: str,
    papel: str,
    pergunta: str,
    resposta: str | None = None,
    sessao_id: str | None = None,
    bloqueada: bool = False,
    motivos: Sequence[str] = (),
    risco: int = 0,
    documentos: Sequence[str] = (),
    latencia_ms: int | None = None,
    modelo: str | None = None,
    trace_id: str | None = None,
    rota: str | None = None,
    custo_simulado: float | None = None,
    custo_referencia: float | None = None,
) -> None:
    """Grava uma pergunta (e a resposta, se houve) na tabela `log_conversas`."""
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO log_conversas (usuario_id, papel, sessao_id, pergunta, resposta, "
                    "bloqueada, motivos, risco, documentos, latencia_ms, modelo, trace_id, rota, custo_simulado, custo_referencia) "
                    "VALUES (:usuario_id, :papel, :sessao_id, :pergunta, :resposta, "
                    ":bloqueada, :motivos, :risco, :documentos, :latencia_ms, :modelo, :trace_id, :rota, :custo_simulado, :custo_referencia)"
                ),
                {
                    "usuario_id": usuario_id,
                    "papel": papel,
                    "sessao_id": sessao_id,
                    "pergunta": _clean(pergunta),
                    "resposta": _clean(resposta),
                    "bloqueada": bloqueada,
                    "motivos": list(motivos),
                    "risco": risco,
                    "documentos": list(documentos),
                    "latencia_ms": latencia_ms,
                    "modelo": modelo,
                    "trace_id": trace_id,
                    "rota": rota,
                    "custo_simulado": custo_simulado,
                    "custo_referencia": custo_referencia,
                },
            )
    except Exception:
        logger.exception("Não foi possível gravar o log da conversa.")


def log_event(engine: Engine, tipo: str, usuario: str | None = None, detalhe: str | None = None) -> None:
    """Grava um evento de segurança na tabela `eventos_seguranca`."""
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO eventos_seguranca (tipo, usuario, detalhe) VALUES (:tipo, :usuario, :detalhe)"),
                {
                    "tipo": tipo,
                    "usuario": (usuario or "")[:80] or None,
                    "detalhe": _clean(detalhe),
                },
            )
    except Exception:
        logger.exception("Não foi possível gravar o evento de segurança.")


def log_tool_call(
    engine: Engine,
    *,
    trace_id: str,
    usuario_id: str,
    papel: str,
    servidor: str,
    ferramenta: str,
    argumentos: dict,
    status: str,
    resultado: str | None = None,
    duracao_ms: int | None = None,
    confirmada: bool | None = None,
) -> None:
    """Grava uma chamada de ferramenta do agente em `tool_calls` (argumentos e resultado redigidos)."""
    import json

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tool_calls (trace_id, usuario_id, papel, servidor, ferramenta, argumentos, "
                    "status, resultado, duracao_ms, confirmada) VALUES (:trace_id, :usuario_id, :papel, "
                    ":servidor, :ferramenta, CAST(:argumentos AS JSONB), :status, :resultado, :duracao_ms, :confirmada)"
                ),
                {
                    "trace_id": trace_id,
                    "usuario_id": usuario_id,
                    "papel": papel,
                    "servidor": servidor,
                    "ferramenta": ferramenta,
                    "argumentos": json.dumps(_redact_values(argumentos), ensure_ascii=False, default=str),
                    "status": status,
                    "resultado": _clean(resultado),
                    "duracao_ms": duracao_ms,
                    "confirmada": confirmada,
                },
            )
    except Exception:
        logger.exception("Não foi possível gravar o rastro da ferramenta.")
