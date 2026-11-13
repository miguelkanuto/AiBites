"""Testes unitários da política de acesso (sem banco, sem modelo)."""

import pytest
from rbac import (
    NIVEIS,
    Usuario,
    build_access_filters,
    filtrar_resultados,
    niveis_permitidos,
    pode_ver,
)

from conftest import (
    CEO_HELENA,
    CLIENTE_PAULO,
    GERENTE_MARCOS,
    RH_JULIANA,
    TI_RODRIGO,
    VENDEDOR_CARLOS,
)


class FakeNode:
    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata


@pytest.mark.parametrize(
    ("usuario", "nivel", "esperado"),
    [
        (CLIENTE_PAULO, "publico", True),
        (CLIENTE_PAULO, "interno", False),
        (CLIENTE_PAULO, "vendas", False),
        (CLIENTE_PAULO, "rh", False),
        (CLIENTE_PAULO, "diretoria", False),
        (VENDEDOR_CARLOS, "interno", True),
        (VENDEDOR_CARLOS, "vendas", False),
        (VENDEDOR_CARLOS, "rh", False),
        (TI_RODRIGO, "rh", False),
        (TI_RODRIGO, "vendas", False),
        (GERENTE_MARCOS, "vendas", True),
        (GERENTE_MARCOS, "rh", False),
        (RH_JULIANA, "rh", True),
        (RH_JULIANA, "diretoria", False),
        (RH_JULIANA, "vendas", False),
        (CEO_HELENA, "diretoria", True),
        (CEO_HELENA, "rh", True),
    ],
)
def test_matriz_de_niveis_por_papel(usuario: Usuario, nivel: str, esperado: bool) -> None:
    assert pode_ver(usuario, {"nivel": nivel}) is esperado


def test_funcionario_ve_o_proprio_documento_restrito() -> None:
    proprio = {"nivel": "rh", "dono": VENDEDOR_CARLOS.funcionario_id}
    de_outro = {"nivel": "rh", "dono": "F006"}

    assert pode_ver(VENDEDOR_CARLOS, proprio) is True
    assert pode_ver(VENDEDOR_CARLOS, de_outro) is False


def test_vendedor_ve_apenas_as_proprias_vendas() -> None:
    assert pode_ver(VENDEDOR_CARLOS, {"nivel": "vendas", "dono": "F002"}) is True
    assert pode_ver(VENDEDOR_CARLOS, {"nivel": "vendas", "dono": "F006"}) is False
    assert pode_ver(VENDEDOR_CARLOS, {"nivel": "vendas"}) is False


def test_salario_do_ceo_so_para_o_proprio_ceo() -> None:
    salario_ceo = {"nivel": "diretoria", "dono": "F014"}

    permitidos = [
        usuario.nome
        for usuario in (VENDEDOR_CARLOS, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, CLIENTE_PAULO, CEO_HELENA)
        if pode_ver(usuario, salario_ceo)
    ]

    assert permitidos == [CEO_HELENA.nome]


def test_cliente_nunca_usa_a_regra_do_proprio_documento() -> None:
    # Cliente não tem funcionario_id, então um documento com `dono` não casa.
    assert pode_ver(CLIENTE_PAULO, {"nivel": "rh", "dono": "C001"}) is False


def test_papel_desconhecido_nao_ve_nada() -> None:
    intruso = Usuario("X", "Intruso", "administrador", funcionario_id="F002")

    assert niveis_permitidos("administrador") == ()
    assert all(pode_ver(intruso, {"nivel": nivel}) is False for nivel in NIVEIS)
    assert pode_ver(intruso, {"nivel": "rh", "dono": "F002"}) is False


def test_documento_sem_nivel_e_negado() -> None:
    assert pode_ver(CEO_HELENA, {"tipo": "produto"}) is False


def test_filtrar_resultados_remove_o_que_nao_pode() -> None:
    nodes = [
        FakeNode({"nivel": "publico"}),
        FakeNode({"nivel": "rh", "dono": "F006"}),
        FakeNode({"nivel": "diretoria", "dono": "F014"}),
        FakeNode({"nivel": "vendas", "dono": "F002"}),
    ]

    restantes = filtrar_resultados(VENDEDOR_CARLOS, nodes)

    assert [n.metadata["nivel"] for n in restantes] == ["publico", "vendas"]


def test_filtro_do_banco_reflete_a_politica() -> None:
    filtro = build_access_filters(VENDEDOR_CARLOS)

    chaves = {f.key: f.value for f in filtro.filters}
    assert chaves["nivel"] == ["publico", "interno"]
    assert chaves["dono"] == "F002"
    assert filtro.condition.value == "or"


def test_filtro_do_cliente_nao_tem_regra_de_dono() -> None:
    filtro = build_access_filters(CLIENTE_PAULO)

    assert [f.key for f in filtro.filters] == ["nivel"]
    assert filtro.filters[0].value == ["publico"]


def test_filtro_de_papel_desconhecido_nao_casa_com_nada() -> None:
    filtro = build_access_filters(Usuario("X", "Intruso", "administrador", funcionario_id="F002"))

    assert [f.key for f in filtro.filters] == ["nivel"]
    assert filtro.filters[0].value == ["__nenhum__"]
