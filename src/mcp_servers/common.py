"""Peças comuns dos servidores MCP: autorização, respostas e bancos fictícios.

Cada servidor roda como um processo separado (stdio) e simula um sistema
externo: RH, Softdesk/Jira (TI), Slack e um serviço de números de vendas.
"""

import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent.parent
BASE_DIR = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

_ = load_dotenv(BASE_DIR / ".env")

from ctx_token import verify  # noqa: E402
from rbac import Usuario  # noqa: E402
from tool_policy import pode_usar  # noqa: E402

MOCK_DIR = Path(os.getenv("AIBITES_MOCK_DIR", str(BASE_DIR / "storage" / "mock")))


class AcessoNegado(Exception):
    """O papel do usuário não pode usar a ferramenta ou o recurso pedido."""


def autorizar(ferramenta: str, contexto: str) -> Usuario:
    """Confere o contexto assinado e a política da ferramenta.

    Args:
        ferramenta: Nome no formato `servidor.ferramenta`.
        contexto: Token assinado pelo app.

    Returns:
        O usuário autenticado.

    Raises:
        ContextoInvalido: Contexto ausente, adulterado ou vencido.
        AcessoNegado: Papel sem permissão para a ferramenta.
    """
    usuario = verify(contexto)
    if not pode_usar(usuario.papel, ferramenta):
        raise AcessoNegado(f"O papel '{usuario.papel}' não pode usar {ferramenta}.")
    return usuario


def ok(**dados: Any) -> str:
    """Resposta de sucesso em JSON."""
    return json.dumps({"ok": True, **dados}, ensure_ascii=False, default=str)


def erro(mensagem: str, **extra: Any) -> str:
    """Erro de negócio (entrada inválida, regra violada) em JSON; o modelo pode explicá-lo."""
    return json.dumps({"ok": False, "erro": mensagem, **extra}, ensure_ascii=False, default=str)


def mock_db(nome: str, schema: str) -> sqlite3.Connection:
    """Abre (e cria, se preciso) o banco SQLite do sistema fictício `nome`."""
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(MOCK_DIR / f"{nome}.db", timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.executescript(schema)
    return conexao


def parse_data(valor: str, campo: str) -> date:
    """Converte `AAAA-MM-DD`; levanta `ValueError` com mensagem clara."""
    try:
        return date.fromisoformat(valor.strip())
    except (ValueError, AttributeError) as error:
        raise ValueError(f"{campo} deve estar no formato AAAA-MM-DD (recebido: {valor!r}).") from error


def pg_engine():
    """Engine somente-leitura (usuário do app) para consultar o PostgreSQL de negócio."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["AIBITES_DATABASE_URL"]).set(drivername="postgresql+psycopg2")
    return create_engine(url.render_as_string(hide_password=False), pool_pre_ping=True)
