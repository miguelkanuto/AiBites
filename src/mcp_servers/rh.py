"""Servidor MCP do sistema de RH (fictício): saldo e pedidos de férias.

Regra fictícia: 30 dias de direito por ano completo de casa, acumulando no
máximo 60. Pedidos pendentes e aprovados descontam do saldo.
"""

from datetime import date

from mcp.server.fastmcp import FastMCP

from common import AcessoNegado, autorizar, erro, mock_db, ok, parse_data, pg_engine
from guardrails import redact
from sqlalchemy import text

mcp = FastMCP("rh")

SCHEMA = """
CREATE TABLE IF NOT EXISTS solicitacoes_ferias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo TEXT UNIQUE,
    funcionario_id TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    dias INTEGER NOT NULL,
    observacao TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DIAS_POR_ANO = 30
LIMITE_ACUMULADO = 60
MIN_DIAS = 5
MAX_DIAS = 30


def _alvo(usuario, funcionario_id: str) -> str:
    """Funcionário consultado: o próprio, ou outro só para RH e CEO."""
    alvo = (funcionario_id or "").strip() or usuario.funcionario_id
    if alvo != usuario.funcionario_id and usuario.papel not in ("rh", "ceo"):
        raise AcessoNegado("Você só pode consultar os seus próprios dados de férias.")
    return alvo


def _saldo(funcionario_id: str) -> dict:
    with pg_engine().connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT f.nome, f.data_admissao, g.nome AS gerente FROM funcionarios f "
                "LEFT JOIN funcionarios g ON g.funcionario_id = f.gerente_id WHERE f.funcionario_id = :id"
            ),
            {"id": funcionario_id},
        ).first()
    if linha is None:
        raise ValueError(f"Funcionário {funcionario_id} não encontrado.")

    hoje = date.today()
    anos = hoje.year - linha.data_admissao.year - ((hoje.month, hoje.day) < (linha.data_admissao.month, linha.data_admissao.day))
    direito = min(LIMITE_ACUMULADO, DIAS_POR_ANO * max(anos, 0))

    with mock_db("rh", SCHEMA) as banco:
        usados = banco.execute(
            "SELECT COALESCE(SUM(dias), 0) FROM solicitacoes_ferias "
            "WHERE funcionario_id = ? AND status IN ('pendente', 'aprovada')",
            (funcionario_id,),
        ).fetchone()[0]

    return {
        "funcionario": linha.nome,
        "gerente": linha.gerente,
        "anos_de_casa": anos,
        "dias_de_direito": direito,
        "dias_ja_solicitados": usados,
        "saldo_dias": direito - usados,
    }


@mcp.tool()
def consultar_saldo_ferias(contexto: str, funcionario_id: str = "") -> str:
    """Consulta o saldo de férias (dias de direito, já solicitados e disponíveis).

    Use quando a pessoa perguntar quantos dias de férias ela tem. Sem argumentos,
    consulta a própria pessoa; `funcionario_id` é só para RH e CEO.
    """
    try:
        usuario = autorizar("rh.consultar_saldo_ferias", contexto)
        return ok(**_saldo(_alvo(usuario, funcionario_id)))
    except ValueError as e:
        return erro(str(e))


@mcp.tool()
def listar_solicitacoes_ferias(contexto: str, funcionario_id: str = "") -> str:
    """Lista os pedidos de férias da pessoa (protocolo, datas, dias e status)."""
    usuario = autorizar("rh.listar_solicitacoes_ferias", contexto)
    alvo = _alvo(usuario, funcionario_id)
    with mock_db("rh", SCHEMA) as banco:
        linhas = banco.execute(
            "SELECT protocolo, inicio, fim, dias, status FROM solicitacoes_ferias "
            "WHERE funcionario_id = ? ORDER BY id DESC LIMIT 20",
            (alvo,),
        ).fetchall()
    return ok(solicitacoes=[dict(linha) for linha in linhas])


@mcp.tool()
def solicitar_ferias(contexto: str, data_inicio: str, data_fim: str, observacao: str = "") -> str:
    """Registra um pedido de férias para a própria pessoa, que segue para aprovação do gestor.

    Datas no formato AAAA-MM-DD. Mínimo de 5 e máximo de 30 dias, começando no
    futuro, dentro do saldo e sem sobrepor outro pedido. Só chame depois de ter
    as duas datas; se faltar alguma, pergunte à pessoa.
    """
    usuario = autorizar("rh.solicitar_ferias", contexto)
    try:
        inicio = parse_data(data_inicio, "data_inicio")
        fim = parse_data(data_fim, "data_fim")
    except ValueError as e:
        return erro(str(e))

    if fim < inicio:
        return erro("A data final não pode ser anterior à inicial.")
    if inicio <= date.today():
        return erro("O início das férias precisa ser uma data futura.")

    dias = (fim - inicio).days + 1
    if not MIN_DIAS <= dias <= MAX_DIAS:
        return erro(f"O pedido precisa ter entre {MIN_DIAS} e {MAX_DIAS} dias (pedido: {dias}).")

    saldo = _saldo(usuario.funcionario_id)
    if dias > saldo["saldo_dias"]:
        return erro(f"Saldo insuficiente: você tem {saldo['saldo_dias']} dia(s) e pediu {dias}.", saldo_dias=saldo["saldo_dias"])

    with mock_db("rh", SCHEMA) as banco:
        conflito = banco.execute(
            "SELECT protocolo FROM solicitacoes_ferias WHERE funcionario_id = ? "
            "AND status IN ('pendente', 'aprovada') AND inicio <= ? AND fim >= ?",
            (usuario.funcionario_id, fim.isoformat(), inicio.isoformat()),
        ).fetchone()
        if conflito:
            return erro(f"O período se sobrepõe ao pedido {conflito['protocolo']}.")

        cursor = banco.execute(
            "INSERT INTO solicitacoes_ferias (funcionario_id, inicio, fim, dias, observacao) VALUES (?, ?, ?, ?, ?)",
            (usuario.funcionario_id, inicio.isoformat(), fim.isoformat(), dias, redact(observacao or "")[:300]),
        )
        protocolo = f"FER-{inicio.year}-{cursor.lastrowid:04d}"
        banco.execute("UPDATE solicitacoes_ferias SET protocolo = ? WHERE id = ?", (protocolo, cursor.lastrowid))

    return ok(
        protocolo=protocolo,
        inicio=inicio.isoformat(),
        fim=fim.isoformat(),
        dias=dias,
        status="pendente de aprovação do gestor",
        gestor=saldo["gerente"],
        saldo_restante=saldo["saldo_dias"] - dias,
    )


if __name__ == "__main__":
    mcp.run()
