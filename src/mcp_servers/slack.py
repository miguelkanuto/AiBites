"""Servidor MCP de mensagens (fictício, estilo Slack): canais de trabalho."""

from mcp.server.fastmcp import FastMCP

from common import AcessoNegado, autorizar, erro, mock_db, ok
from guardrails import redact
from tool_policy import CANAIS, canais_permitidos

mcp = FastMCP("slack")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal TEXT NOT NULL,
    remetente_id TEXT NOT NULL,
    texto TEXT NOT NULL,
    enviado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MAX_TEXTO = 500


@mcp.tool()
def listar_canais(contexto: str) -> str:
    """Lista os canais em que a pessoa pode postar mensagens."""
    usuario = autorizar("slack.listar_canais", contexto)
    return ok(canais=canais_permitidos(usuario.papel))


@mcp.tool()
def enviar_mensagem(contexto: str, canal: str, texto: str) -> str:
    """Envia uma mensagem de trabalho a um canal (ex.: #vendas, #ti, #rh, #geral).

    O texto vai em nome da própria pessoa, com até 500 caracteres. Só use para
    mensagens que a pessoa pediu para enviar, com o conteúdo que ela indicou.
    """
    usuario = autorizar("slack.enviar_mensagem", contexto)
    canal = canal.strip().lower()
    if canal and not canal.startswith("#"):
        canal = "#" + canal

    if canal not in CANAIS:
        return erro(f"Canal desconhecido. Canais existentes: {', '.join(sorted(CANAIS))}.")
    if usuario.papel not in CANAIS[canal]:
        raise AcessoNegado(f"O papel '{usuario.papel}' não pode postar em {canal}.")

    texto = redact(texto.strip())
    if not texto:
        return erro("A mensagem está vazia.")
    if len(texto) > MAX_TEXTO:
        return erro(f"A mensagem passa de {MAX_TEXTO} caracteres (tem {len(texto)}).")

    with mock_db("slack", SCHEMA) as banco:
        cursor = banco.execute(
            "INSERT INTO mensagens (canal, remetente_id, texto) VALUES (?, ?, ?)",
            (canal, usuario.funcionario_id, texto),
        )

    return ok(mensagem_id=cursor.lastrowid, canal=canal, texto=texto)


if __name__ == "__main__":
    mcp.run()
