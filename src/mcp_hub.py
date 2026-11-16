"""Cliente MCP do app: sobe os servidores de ferramentas e chama as ferramentas.

Cada servidor (RH, TI, Slack, vendas) é um processo separado falando MCP por
stdio. O hub os inicia uma vez, lista as ferramentas e repassa as chamadas.
O hub não decide permissões: isso é do agente (`agent.py`) e dos próprios servidores.
"""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import importlib.util

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

logger = logging.getLogger(__name__)

SERVERS_DIR = Path(__file__).resolve().parent / "mcp_servers"


def load_server_module(server: str) -> Any:
    """Importa o módulo de um servidor MCP para rodar no mesmo processo.

    Os servidores importam `common` pelo nome simples (rodam como script), então a
    pasta deles entra no `sys.path`. O módulo recebe um nome próprio para não colidir
    com pacotes de mesmo nome (ex.: `slack`).
    """
    if str(SERVERS_DIR) not in sys.path:
        sys.path.append(str(SERVERS_DIR))
    name = f"aibites_mcp_{server}"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SERVERS_DIR / f"{server}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"Servidor MCP não encontrado: {server}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

SERVER_NAMES = ("rh", "ti", "slack", "vendas")
CALL_TIMEOUT_SECONDS = 30
START_TIMEOUT_SECONDS = 60
CONTEXT_ARGUMENT = "contexto"


@dataclass(frozen=True)
class ToolInfo:
    """Ferramenta publicada por um servidor.

    Attributes:
        qualified_name: `servidor.ferramenta`.
        server: Nome do servidor.
        name: Nome da ferramenta no servidor.
        description: Texto que o modelo lê para decidir quando usar.
        schema: JSON Schema dos argumentos, sem o argumento de contexto (o modelo não o vê).
    """

    qualified_name: str
    server: str
    name: str
    description: str
    schema: dict[str, Any]


def public_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove do schema o argumento `contexto`, que só o app preenche."""
    properties = {k: v for k, v in schema.get("properties", {}).items() if k != CONTEXT_ARGUMENT}
    required = [name for name in schema.get("required", []) if name != CONTEXT_ARGUMENT]
    cleaned = {**schema, "type": "object", "properties": properties}
    if required:
        cleaned["required"] = required
    else:
        cleaned.pop("required", None)
    cleaned.pop("title", None)
    return cleaned


class McpHub:
    """Mantém os servidores MCP rodando e expõe `catalog()` e `call()`."""

    def __init__(self, servers: tuple[str, ...] = SERVER_NAMES, mode: str | None = None) -> None:
        self._servers = servers
        self._mode = mode or os.getenv("AIBITES_MCP_MODE", "stdio")
        if self._mode not in ("stdio", "inprocess"):
            raise ValueError(f"AIBITES_MCP_MODE inválido: {self._mode!r} (use 'stdio' ou 'inprocess').")
        self._sessions: dict[str, ClientSession] = {}
        self._tools: list[ToolInfo] = []
        self._failures: dict[str, str] = {}
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Inicia os servidores (uma única vez) e espera a lista de ferramentas."""
        async with self._lock:
            if self._task is None:
                self._task = asyncio.create_task(self._run(), name="mcp-hub")
        await asyncio.wait_for(self._ready.wait(), timeout=START_TIMEOUT_SECONDS)

    async def stop(self) -> None:
        """Encerra os servidores."""
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

    async def _run(self) -> None:
        # Os contextos do stdio precisam abrir e fechar na mesma tarefa.
        try:
            async with AsyncExitStack() as stack:
                for server in self._servers:
                    try:
                        await self._start_server(stack, server)
                    except Exception as error:
                        logger.exception("Servidor MCP '%s' não iniciou.", server)
                        self._failures[server] = str(error)
                self._ready.set()
                await self._stop.wait()
        finally:
            self._ready.set()
            self._sessions.clear()

    async def _start_server(self, stack: AsyncExitStack, server: str) -> None:
        if self._mode == "inprocess":
            # Mesmo protocolo MCP, por memória, sem processo separado (cada um custa ~60 MB).
            module = load_server_module(server)
            session = await stack.enter_async_context(
                create_connected_server_and_client_session(module.mcp._mcp_server)
            )
        else:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVERS_DIR / f"{server}.py")],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            read, write = await stack.enter_async_context(stdio_client(parameters))
            session = await stack.enter_async_context(ClientSession(read, write))
            await asyncio.wait_for(session.initialize(), timeout=START_TIMEOUT_SECONDS)

        self._sessions[server] = session
        for tool in (await session.list_tools()).tools:
            self._tools.append(
                ToolInfo(
                    qualified_name=f"{server}.{tool.name}",
                    server=server,
                    name=tool.name,
                    description=(tool.description or "").strip(),
                    schema=public_schema(tool.inputSchema or {}),
                )
            )

    def catalog(self) -> list[ToolInfo]:
        """Ferramentas publicadas pelos servidores que subiram."""
        return list(self._tools)

    @property
    def failures(self) -> dict[str, str]:
        """Servidores que não iniciaram e o motivo."""
        return dict(self._failures)

    async def call(self, qualified_name: str, arguments: dict[str, Any], context_token: str) -> tuple[str, bool]:
        """Chama uma ferramenta, injetando o contexto assinado do usuário.

        Args:
            qualified_name: `servidor.ferramenta`.
            arguments: Argumentos escolhidos pelo modelo (o campo de contexto, se vier, é descartado).
            context_token: Contexto assinado pelo app (`ctx_token.sign`).

        Returns:
            Tupla `(texto, houve_erro)` com a resposta da ferramenta.
        """
        server, _, name = qualified_name.partition(".")
        session = self._sessions.get(server)
        if session is None:
            return f"Servidor '{server}' indisponível.", True

        safe_arguments = {k: v for k, v in arguments.items() if k != CONTEXT_ARGUMENT}
        safe_arguments[CONTEXT_ARGUMENT] = context_token

        try:
            result = await asyncio.wait_for(session.call_tool(name, safe_arguments), timeout=CALL_TIMEOUT_SECONDS)
        except TimeoutError:
            return f"A ferramenta {qualified_name} demorou demais.", True

        text = "\n".join(block.text for block in result.content if getattr(block, "text", None))
        return text or "(sem conteúdo)", bool(result.isError)
