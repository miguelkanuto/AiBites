"""Servidor MCP de números de vendas: somas e rankings exatos em SQL.

Aqui está o "submodelo de matemática": o modelo de linguagem não calcula nada,
só escolhe a ferramenta e os filtros; o PostgreSQL faz a conta, com consultas
parametrizadas e só leitura. Contam apenas vendas com status `Concluída`.
"""

from mcp.server.fastmcp import FastMCP

from common import AcessoNegado, autorizar, erro, ok, parse_data, pg_engine
from sqlalchemy import text

mcp = FastMCP("vendas")

CONCLUIDA = "Concluída"


def _vendedor_do_usuario(usuario) -> str:
    with pg_engine().connect() as conexao:
        linha = conexao.execute(
            text("SELECT vendedor_id FROM funcionarios WHERE funcionario_id = :f"),
            {"f": usuario.funcionario_id},
        ).first()
    if linha is None or linha.vendedor_id is None:
        raise AcessoNegado("Seu usuário não está ligado a um vendedor.")
    return linha.vendedor_id


def _periodo(data_inicio: str, data_fim: str) -> tuple[str, dict]:
    filtros, parametros = [], {}
    if data_inicio.strip():
        parametros["inicio"] = parse_data(data_inicio, "data_inicio")
        filtros.append("v.data_venda >= :inicio")
    if data_fim.strip():
        parametros["fim"] = parse_data(data_fim, "data_fim")
        filtros.append("v.data_venda <= :fim")
    if "inicio" in parametros and "fim" in parametros and parametros["fim"] < parametros["inicio"]:
        raise ValueError("A data final não pode ser anterior à inicial.")
    return "".join(f" AND {f}" for f in filtros), parametros


def _escopo_do_vendedor(usuario, vendedor_id: str) -> str:
    """Vendedor só vê o próprio; gerente e CEO veem o que pedirem (vazio = todos)."""
    pedido = vendedor_id.strip().upper()
    if usuario.papel == "vendedor":
        proprio = _vendedor_do_usuario(usuario)
        if pedido and pedido != proprio:
            raise AcessoNegado("Você só pode consultar as suas próprias vendas.")
        return proprio
    return pedido


@mcp.tool()
def total_vendido(
    contexto: str,
    data_inicio: str = "",
    data_fim: str = "",
    vendedor_id: str = "",
    produto_id: str = "",
    categoria: str = "",
    regiao: str = "",
) -> str:
    """Calcula o total vendido (R$), o número de vendas e de unidades, com filtros opcionais.

    Use para qualquer pergunta de soma ou contagem ("quanto vendeu", "total de").
    Datas em AAAA-MM-DD. Filtros: vendedor_id (ex.: V002), produto_id (ex.: P001),
    categoria (ex.: Informática), regiao (ex.: Sul). Vendedores só consultam as
    próprias vendas. Conta apenas vendas concluídas.
    """
    usuario = autorizar("vendas.total_vendido", contexto)
    try:
        periodo, parametros = _periodo(data_inicio, data_fim)
    except ValueError as e:
        return erro(str(e))

    filtros = periodo
    vendedor = _escopo_do_vendedor(usuario, vendedor_id)
    if vendedor:
        filtros += " AND v.vendedor_id = :vendedor"
        parametros["vendedor"] = vendedor
    if produto_id.strip():
        filtros += " AND v.produto_id = :produto"
        parametros["produto"] = produto_id.strip().upper()
    if categoria.strip():
        filtros += " AND lower(p.categoria) = lower(:categoria)"
        parametros["categoria"] = categoria.strip()
    if regiao.strip():
        filtros += " AND lower(s.regiao) = lower(:regiao)"
        parametros["regiao"] = regiao.strip()

    with pg_engine().connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT COALESCE(SUM(v.valor_total), 0) AS total, COUNT(*) AS vendas, "
                "COALESCE(SUM(v.quantidade), 0) AS unidades FROM vendas v "
                "JOIN produtos p ON p.produto_id = v.produto_id "
                "JOIN vendedores s ON s.vendedor_id = v.vendedor_id "
                "WHERE v.status = :status" + filtros
            ),
            {"status": CONCLUIDA, **parametros},
        ).one()

    return ok(
        total_vendido=float(linha.total),
        numero_de_vendas=linha.vendas,
        unidades=int(linha.unidades),
        filtros={k: str(v) for k, v in parametros.items()},
        observacao="Somente vendas concluídas.",
    )


@mcp.tool()
def ranking_vendedores(contexto: str, data_inicio: str = "", data_fim: str = "", top: int = 5) -> str:
    """Ranking dos vendedores por valor vendido (só gerente de vendas e CEO).

    Datas em AAAA-MM-DD; `top` de 1 a 10. Conta apenas vendas concluídas.
    """
    autorizar("vendas.ranking_vendedores", contexto)
    if not 1 <= top <= 10:
        return erro("`top` deve estar entre 1 e 10.")
    try:
        periodo, parametros = _periodo(data_inicio, data_fim)
    except ValueError as e:
        return erro(str(e))

    with pg_engine().connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT s.vendedor_id, s.nome, COALESCE(SUM(v.valor_total), 0) AS total, COUNT(*) AS vendas "
                "FROM vendas v JOIN vendedores s ON s.vendedor_id = v.vendedor_id "
                "WHERE v.status = :status" + periodo + " GROUP BY s.vendedor_id, s.nome "
                "ORDER BY total DESC LIMIT :top"
            ),
            {"status": CONCLUIDA, "top": top, **parametros},
        ).all()

    return ok(
        ranking=[
            {"posicao": i, "vendedor_id": l.vendedor_id, "nome": l.nome, "total_vendido": float(l.total), "numero_de_vendas": l.vendas}
            for i, l in enumerate(linhas, start=1)
        ],
        observacao="Somente vendas concluídas.",
    )


@mcp.tool()
def total_por_categoria(contexto: str, data_inicio: str = "", data_fim: str = "", vendedor_id: str = "") -> str:
    """Total vendido (R$) por categoria de produto, em ordem decrescente.

    Datas em AAAA-MM-DD. Vendedores só veem as próprias vendas. Conta apenas vendas concluídas.
    """
    usuario = autorizar("vendas.total_por_categoria", contexto)
    try:
        periodo, parametros = _periodo(data_inicio, data_fim)
    except ValueError as e:
        return erro(str(e))

    vendedor = _escopo_do_vendedor(usuario, vendedor_id)
    filtros = periodo
    if vendedor:
        filtros += " AND v.vendedor_id = :vendedor"
        parametros["vendedor"] = vendedor

    with pg_engine().connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT p.categoria, COALESCE(SUM(v.valor_total), 0) AS total, COUNT(*) AS vendas "
                "FROM vendas v JOIN produtos p ON p.produto_id = v.produto_id "
                "WHERE v.status = :status" + filtros + " GROUP BY p.categoria ORDER BY total DESC"
            ),
            {"status": CONCLUIDA, **parametros},
        ).all()

    return ok(
        categorias=[{"categoria": l.categoria, "total_vendido": float(l.total), "numero_de_vendas": l.vendas} for l in linhas],
        observacao="Somente vendas concluídas.",
    )


if __name__ == "__main__":
    mcp.run()
