"""Testes de integração dos servidores MCP (processos reais, bancos fictícios em pasta temporária).

Não chamam o LLM. As ferramentas de RH e vendas leem o PostgreSQL (usuário do app).
"""

import asyncio
import json
import os
import tempfile
from datetime import date, timedelta

import ctx_token
import pytest
from sqlalchemy import text

from conftest import CEO_HELENA, CLIENTE_PAULO, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, VENDEDOR_CARLOS, VENDEDOR_RAFAEL

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", params=["stdio", "inprocess"])
def mundo(request):
    """Os mesmos testes rodam com os servidores em processos separados e em memória."""
    if not os.getenv("AIBITES_DATABASE_URL"):
        pytest.skip("AIBITES_DATABASE_URL não configurada")

    from mcp_hub import McpHub

    pasta = tempfile.mkdtemp(prefix="aibites_mock_")
    anterior = {chave: os.environ.get(chave) for chave in ("AIBITES_MOCK_DIR", "MCP_CONTEXT_SECRET")}
    os.environ["AIBITES_MOCK_DIR"] = pasta
    os.environ["MCP_CONTEXT_SECRET"] = "segredo-de-teste"

    loop = asyncio.new_event_loop()
    hub = McpHub(mode=request.param)
    loop.run_until_complete(hub.start())
    assert hub.failures == {}, hub.failures

    def chamar(usuario, nome, **argumentos):
        texto, erro = loop.run_until_complete(hub.call(nome, argumentos, ctx_token.sign(usuario)))
        return texto, erro

    def chamar_com_token(nome, token, **argumentos):
        return loop.run_until_complete(hub.call(nome, argumentos, token))

    chamar.com_token = chamar_com_token  # type: ignore[attr-defined]

    yield hub, chamar

    loop.run_until_complete(hub.stop())
    loop.close()
    for chave, valor in anterior.items():
        if valor is None:
            os.environ.pop(chave, None)
        else:
            os.environ[chave] = valor


def dados(texto: str) -> dict:
    return json.loads(texto)


def futuro(dias: int) -> date:
    return date.today() + timedelta(days=dias)


# --- Catálogo ---


def test_todos_os_servidores_sobem_e_publicam_ferramentas(mundo) -> None:
    hub, _ = mundo

    nomes = {t.qualified_name for t in hub.catalog()}

    assert {"rh.solicitar_ferias", "ti.abrir_ticket", "slack.enviar_mensagem", "vendas.total_vendido"} <= nomes
    assert all(ferramenta.server in ("rh", "ti", "slack", "vendas") for ferramenta in hub.catalog())


def test_o_modelo_nunca_ve_o_argumento_de_contexto(mundo) -> None:
    hub, _ = mundo

    for ferramenta in hub.catalog():
        assert "contexto" not in ferramenta.schema.get("properties", {})
        assert "contexto" not in ferramenta.schema.get("required", [])


# --- Contexto e permissão no servidor ---


@pytest.mark.parametrize("token", ["", "abc.def", "texto"])
def test_servidor_recusa_contexto_invalido(mundo, token: str) -> None:
    _, chamar = mundo

    texto, erro = chamar.com_token("vendas.total_vendido", token)

    assert erro is True
    assert "Contexto" in texto or "Assinatura" in texto


def test_servidor_recusa_contexto_assinado_com_outro_segredo(mundo) -> None:
    _, chamar = mundo
    os.environ["MCP_CONTEXT_SECRET"] = "outro-segredo"
    try:
        token = ctx_token.sign(CEO_HELENA)
    finally:
        os.environ["MCP_CONTEXT_SECRET"] = "segredo-de-teste"

    texto, erro = chamar.com_token("vendas.ranking_vendedores", token, top=3)

    assert erro is True and "Assinatura" in texto


def test_cliente_nao_usa_ferramentas(mundo) -> None:
    _, chamar = mundo
    casos = [
        ("vendas.total_vendido", {}),
        ("rh.consultar_saldo_ferias", {}),
        ("ti.abrir_ticket", {"titulo": "Titulo valido", "descricao": "Descrição com tamanho suficiente."}),
        ("slack.listar_canais", {}),
    ]

    for nome, argumentos in casos:
        texto, erro = chamar(CLIENTE_PAULO, nome, **argumentos)
        assert erro is True, nome
        assert "não pode usar" in texto, nome


def test_vendedor_nao_usa_ferramentas_de_gestao(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(VENDEDOR_CARLOS, "vendas.ranking_vendedores", top=3)
    assert erro is True and "não pode usar" in texto

    texto, erro = chamar(VENDEDOR_CARLOS, "ti.listar_fila")
    assert erro is True


# --- Vendas: contas exatas e escopo ---


def test_total_vendido_bate_com_a_conta_feita_direto_no_banco(mundo) -> None:
    import main

    _, chamar = mundo
    with main.get_engine().connect() as conexao:
        esperado = conexao.execute(
            text(
                "SELECT COALESCE(SUM(v.valor_total), 0) FROM vendas v JOIN produtos p USING (produto_id) "
                "WHERE v.status = 'Concluída' AND v.vendedor_id = 'V002' AND p.categoria = 'Informática'"
            )
        ).scalar_one()

    texto, erro = chamar(VENDEDOR_CARLOS, "vendas.total_vendido", categoria="Informática")

    assert erro is False
    assert dados(texto)["total_vendido"] == pytest.approx(float(esperado))


def test_vendedor_so_consulta_as_proprias_vendas(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(VENDEDOR_CARLOS, "vendas.total_vendido", vendedor_id="V001")
    assert erro is True and "próprias" in texto

    proprio, _ = chamar(VENDEDOR_CARLOS, "vendas.total_vendido")
    explicito, _ = chamar(VENDEDOR_CARLOS, "vendas.total_vendido", vendedor_id="V002")
    assert dados(proprio)["total_vendido"] == dados(explicito)["total_vendido"]


def test_gerente_e_ceo_consultam_qualquer_vendedor(mundo) -> None:
    _, chamar = mundo

    for usuario in (GERENTE_MARCOS, CEO_HELENA):
        texto, erro = chamar(usuario, "vendas.total_vendido", vendedor_id="V001")
        assert erro is False
        assert dados(texto)["filtros"]["vendedor"] == "V001"


def test_ranking_vem_ordenado_e_respeita_o_top(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(GERENTE_MARCOS, "vendas.ranking_vendedores", top=4)

    ranking = dados(texto)["ranking"]
    assert erro is False and len(ranking) == 4
    totais = [item["total_vendido"] for item in ranking]
    assert totais == sorted(totais, reverse=True)


def test_ranking_recusa_top_fora_do_limite(mundo) -> None:
    _, chamar = mundo

    assert dados(chamar(GERENTE_MARCOS, "vendas.ranking_vendedores", top=0)[0])["ok"] is False
    assert dados(chamar(GERENTE_MARCOS, "vendas.ranking_vendedores", top=11)[0])["ok"] is False


def test_filtro_com_sql_injection_nao_quebra_nem_vaza(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(GERENTE_MARCOS, "vendas.total_vendido", categoria="x' OR '1'='1")

    assert erro is False
    assert dados(texto)["numero_de_vendas"] == 0


def test_data_invalida_vira_erro_de_negocio(mundo) -> None:
    _, chamar = mundo

    assert dados(chamar(GERENTE_MARCOS, "vendas.total_vendido", data_inicio="ontem")[0])["ok"] is False
    assert dados(chamar(GERENTE_MARCOS, "vendas.total_vendido", data_inicio="2026-05-01", data_fim="2026-04-01")[0])["ok"] is False


# --- RH ---


def test_saldo_de_ferias_do_proprio_usuario(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(VENDEDOR_CARLOS, "rh.consultar_saldo_ferias")

    assert erro is False
    assert dados(texto)["funcionario"] == "Carlos Lima"


def test_so_rh_e_ceo_consultam_ferias_de_outros(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(VENDEDOR_CARLOS, "rh.consultar_saldo_ferias", funcionario_id="F006")
    assert erro is True and "seus próprios" in texto

    for usuario in (RH_JULIANA, CEO_HELENA):
        texto, erro = chamar(usuario, "rh.consultar_saldo_ferias", funcionario_id="F006")
        assert erro is False and dados(texto)["funcionario"] == "Rafael Martins"


def test_pedido_de_ferias_valido_gera_protocolo_e_desconta_do_saldo(mundo) -> None:
    _, chamar = mundo
    antes = dados(chamar(VENDEDOR_RAFAEL, "rh.consultar_saldo_ferias")[0])["saldo_dias"]
    inicio = futuro(60)

    texto, erro = chamar(
        VENDEDOR_RAFAEL, "rh.solicitar_ferias", data_inicio=inicio.isoformat(), data_fim=(inicio + timedelta(days=9)).isoformat()
    )

    resultado = dados(texto)
    assert erro is False and resultado["ok"] is True
    assert resultado["protocolo"].startswith("FER-") and resultado["dias"] == 10
    assert resultado["status"].startswith("pendente")
    depois = dados(chamar(VENDEDOR_RAFAEL, "rh.consultar_saldo_ferias")[0])["saldo_dias"]
    assert depois == antes - 10


def test_pedido_de_ferias_sobreposto_e_recusado(mundo) -> None:
    _, chamar = mundo
    inicio = futuro(120)
    chamar(VENDEDOR_CARLOS, "rh.solicitar_ferias", data_inicio=inicio.isoformat(), data_fim=(inicio + timedelta(days=7)).isoformat())

    texto, _ = chamar(
        VENDEDOR_CARLOS,
        "rh.solicitar_ferias",
        data_inicio=(inicio + timedelta(days=3)).isoformat(),
        data_fim=(inicio + timedelta(days=12)).isoformat(),
    )

    assert dados(texto)["ok"] is False and "sobrepõe" in dados(texto)["erro"]


@pytest.mark.parametrize(
    ("inicio", "fim", "trecho"),
    [
        (-5, 5, "futura"),  # começa no passado
        (30, 32, "entre 5 e 30"),  # curto demais
        (30, 70, "entre 5 e 30"),  # longo demais
        (40, 35, "anterior"),  # fim antes do início
    ],
)
def test_pedido_de_ferias_invalido_e_recusado(mundo, inicio: int, fim: int, trecho: str) -> None:
    _, chamar = mundo

    texto, erro = chamar(
        VENDEDOR_RAFAEL, "rh.solicitar_ferias", data_inicio=futuro(inicio).isoformat(), data_fim=futuro(fim).isoformat()
    )

    assert dados(texto)["ok"] is False and trecho in dados(texto)["erro"]


def test_pedido_de_ferias_acima_do_saldo_e_recusado(mundo) -> None:
    _, chamar = mundo
    # Gerente tem 60 dias de direito; pede 30 + 30 e depois mais 5.
    primeiro = futuro(200)
    segundo = futuro(260)
    terceiro = futuro(320)
    chamar(GERENTE_MARCOS, "rh.solicitar_ferias", data_inicio=primeiro.isoformat(), data_fim=(primeiro + timedelta(days=29)).isoformat())
    chamar(GERENTE_MARCOS, "rh.solicitar_ferias", data_inicio=segundo.isoformat(), data_fim=(segundo + timedelta(days=29)).isoformat())

    texto, _ = chamar(GERENTE_MARCOS, "rh.solicitar_ferias", data_inicio=terceiro.isoformat(), data_fim=(terceiro + timedelta(days=4)).isoformat())

    assert dados(texto)["ok"] is False and "Saldo insuficiente" in dados(texto)["erro"]


def test_formato_de_data_invalido(mundo) -> None:
    _, chamar = mundo

    texto, _ = chamar(VENDEDOR_RAFAEL, "rh.solicitar_ferias", data_inicio="14/12/2026", data_fim="23/12/2026")

    assert dados(texto)["ok"] is False and "AAAA-MM-DD" in dados(texto)["erro"]


# --- TI ---


def test_abrir_ticket_e_nao_duplicar_em_seguida(mundo) -> None:
    _, chamar = mundo
    argumentos = {"titulo": "VPN não conecta", "descricao": "A VPN dá erro de timeout ao conectar de casa.", "categoria": "rede", "prioridade": "alta"}

    primeiro = dados(chamar(VENDEDOR_CARLOS, "ti.abrir_ticket", **argumentos)[0])
    repetido = dados(chamar(VENDEDOR_CARLOS, "ti.abrir_ticket", **argumentos)[0])

    assert primeiro["ok"] and primeiro["codigo"].startswith("TI-") and primeiro["duplicado"] is False
    assert repetido["codigo"] == primeiro["codigo"] and repetido["duplicado"] is True


@pytest.mark.parametrize(
    "mudanca",
    [
        {"titulo": "oi"},
        {"descricao": "curta"},
        {"categoria": "magia"},
        {"prioridade": "urgentissima"},
    ],
)
def test_ticket_com_dados_invalidos_e_recusado(mundo, mudanca: dict) -> None:
    _, chamar = mundo
    argumentos = {"titulo": "Teclado falhando", "descricao": "Algumas teclas pararam de funcionar hoje.", "categoria": "hardware", "prioridade": "media", **mudanca}

    texto, _ = chamar(VENDEDOR_RAFAEL, "ti.abrir_ticket", **argumentos)

    assert dados(texto)["ok"] is False


def test_so_o_dono_o_ti_e_o_ceo_veem_um_ticket(mundo) -> None:
    _, chamar = mundo
    codigo = dados(
        chamar(
            VENDEDOR_CARLOS,
            "ti.abrir_ticket",
            titulo="Monitor sem imagem",
            descricao="O segundo monitor ficou sem imagem depois da atualização.",
            categoria="hardware",
        )[0]
    )["codigo"]

    texto, erro = chamar(VENDEDOR_RAFAEL, "ti.consultar_ticket", codigo=codigo)
    assert erro is True and "abertos por você" in texto

    for usuario in (VENDEDOR_CARLOS, TI_RODRIGO, CEO_HELENA):
        texto, erro = chamar(usuario, "ti.consultar_ticket", codigo=codigo)
        assert erro is False and dados(texto)["codigo"] == codigo


def test_ti_ve_a_fila_com_prioridade_primeiro(mundo) -> None:
    _, chamar = mundo
    chamar(VENDEDOR_RAFAEL, "ti.abrir_ticket", titulo="Impressora parada", descricao="A impressora do andar não imprime.", prioridade="baixa")
    chamar(VENDEDOR_RAFAEL, "ti.abrir_ticket", titulo="Servidor fora do ar", descricao="O servidor de arquivos caiu agora.", prioridade="critica")

    fila = dados(chamar(TI_RODRIGO, "ti.listar_fila")[0])["fila"]

    assert fila[0]["prioridade"] == "critica"


# --- Slack ---


def test_canais_dependem_do_papel(mundo) -> None:
    _, chamar = mundo

    vendedor = dados(chamar(VENDEDOR_CARLOS, "slack.listar_canais")[0])["canais"]
    ceo = dados(chamar(CEO_HELENA, "slack.listar_canais")[0])["canais"]

    assert "#diretoria" not in vendedor and "#diretoria" in ceo


def test_vendedor_nao_posta_na_diretoria_nem_ti_em_vendas(mundo) -> None:
    _, chamar = mundo

    assert chamar(VENDEDOR_CARLOS, "slack.enviar_mensagem", canal="#diretoria", texto="oi")[1] is True
    assert chamar(TI_RODRIGO, "slack.enviar_mensagem", canal="#vendas", texto="oi")[1] is True


def test_mensagem_sai_com_dados_pessoais_redigidos(mundo) -> None:
    _, chamar = mundo

    texto, erro = chamar(
        VENDEDOR_CARLOS, "slack.enviar_mensagem", canal="vendas", texto="Cliente CPF 529.982.247-25, ligar (11) 91234-5678"
    )

    resultado = dados(texto)
    assert erro is False and resultado["canal"] == "#vendas"
    assert "529.982.247-25" not in resultado["texto"] and "[CPF]" in resultado["texto"] and "[TELEFONE]" in resultado["texto"]


def test_mensagem_vazia_longa_ou_canal_inexistente(mundo) -> None:
    _, chamar = mundo

    assert dados(chamar(VENDEDOR_CARLOS, "slack.enviar_mensagem", canal="#vendas", texto="   ")[0])["ok"] is False
    assert dados(chamar(VENDEDOR_CARLOS, "slack.enviar_mensagem", canal="#vendas", texto="a" * 501)[0])["ok"] is False
    assert dados(chamar(VENDEDOR_CARLOS, "slack.enviar_mensagem", canal="#inexistente", texto="oi")[0])["ok"] is False
