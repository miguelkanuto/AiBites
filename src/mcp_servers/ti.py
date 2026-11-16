"""Servidor MCP do sistema de chamados de TI (fictício, estilo Jira/Softdesk)."""

from mcp.server.fastmcp import FastMCP

from common import AcessoNegado, autorizar, erro, mock_db, ok
from guardrails import redact

mcp = FastMCP("ti")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT UNIQUE,
    solicitante_id TEXT NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    prioridade TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'aberto',
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CATEGORIAS = ("acesso", "hardware", "software", "rede", "outros")
PRIORIDADES = ("baixa", "media", "alta", "critica")
STATUS_ABERTOS = ("aberto", "em_andamento")


def _ticket(linha) -> dict:
    return {
        chave: linha[chave]
        for chave in ("codigo", "titulo", "categoria", "prioridade", "status", "criado_em")
    }


@mcp.tool()
def abrir_ticket(
    contexto: str, titulo: str, descricao: str, categoria: str = "outros", prioridade: str = "media"
) -> str:
    """Abre um chamado para o time de TI, em nome da própria pessoa.

    Categorias: acesso, hardware, software, rede, outros. Prioridades: baixa,
    media, alta, critica. O título deve ter de 5 a 120 caracteres e a descrição de
    10 a 2000. Se a pessoa não disser o problema com clareza, pergunte antes de abrir.
    Um chamado igual (mesmo título) aberto nos últimos 10 minutos não é duplicado.
    """
    usuario = autorizar("ti.abrir_ticket", contexto)
    titulo, descricao = titulo.strip(), descricao.strip()
    categoria, prioridade = categoria.strip().lower(), prioridade.strip().lower()

    if not 5 <= len(titulo) <= 120:
        return erro("O título precisa ter entre 5 e 120 caracteres.")
    if not 10 <= len(descricao) <= 2000:
        return erro("A descrição precisa ter entre 10 e 2000 caracteres.")
    if categoria not in CATEGORIAS:
        return erro(f"Categoria inválida. Use: {', '.join(CATEGORIAS)}.")
    if prioridade not in PRIORIDADES:
        return erro(f"Prioridade inválida. Use: {', '.join(PRIORIDADES)}.")

    with mock_db("ti", SCHEMA) as banco:
        repetido = banco.execute(
            "SELECT * FROM tickets WHERE solicitante_id = ? AND lower(titulo) = lower(?) "
            "AND criado_em > datetime('now', '-10 minutes')",
            (usuario.funcionario_id, titulo),
        ).fetchone()
        if repetido:
            return ok(**_ticket(repetido), duplicado=True, aviso="Já existe um chamado igual aberto agora.")

        cursor = banco.execute(
            "INSERT INTO tickets (solicitante_id, titulo, descricao, categoria, prioridade) VALUES (?, ?, ?, ?, ?)",
            (usuario.funcionario_id, redact(titulo), redact(descricao), categoria, prioridade),
        )
        codigo = f"TI-{1000 + cursor.lastrowid}"
        banco.execute("UPDATE tickets SET codigo = ? WHERE id = ?", (codigo, cursor.lastrowid))
        linha = banco.execute("SELECT * FROM tickets WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return ok(**_ticket(linha), duplicado=False)


@mcp.tool()
def consultar_ticket(contexto: str, codigo: str) -> str:
    """Consulta um chamado pelo código (ex.: TI-1001). Só o dono, o TI e o CEO podem ver."""
    usuario = autorizar("ti.consultar_ticket", contexto)
    with mock_db("ti", SCHEMA) as banco:
        linha = banco.execute("SELECT * FROM tickets WHERE codigo = ?", (codigo.strip().upper(),)).fetchone()

    if linha is None:
        return erro(f"Chamado {codigo} não encontrado.")
    if linha["solicitante_id"] != usuario.funcionario_id and usuario.papel not in ("ti", "ceo"):
        raise AcessoNegado("Você só pode consultar chamados abertos por você.")

    return ok(**_ticket(linha), descricao=linha["descricao"], atualizado_em=linha["atualizado_em"])


@mcp.tool()
def listar_meus_tickets(contexto: str, status: str = "") -> str:
    """Lista os chamados abertos pela própria pessoa. `status` opcional: aberto, em_andamento, fechado."""
    usuario = autorizar("ti.listar_meus_tickets", contexto)
    consulta = "SELECT * FROM tickets WHERE solicitante_id = ?"
    parametros: list = [usuario.funcionario_id]
    if status.strip():
        consulta += " AND status = ?"
        parametros.append(status.strip().lower())

    with mock_db("ti", SCHEMA) as banco:
        linhas = banco.execute(consulta + " ORDER BY id DESC LIMIT 20", parametros).fetchall()
    return ok(tickets=[_ticket(linha) for linha in linhas])


@mcp.tool()
def listar_fila(contexto: str) -> str:
    """Lista a fila de chamados abertos de todos (só para o time de TI e o CEO)."""
    autorizar("ti.listar_fila", contexto)
    with mock_db("ti", SCHEMA) as banco:
        linhas = banco.execute(
            "SELECT * FROM tickets WHERE status IN ('aberto', 'em_andamento') ORDER BY "
            "CASE prioridade WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END, id LIMIT 30"
        ).fetchall()
    return ok(fila=[{**_ticket(linha), "solicitante": linha["solicitante_id"]} for linha in linhas])


if __name__ == "__main__":
    mcp.run()
