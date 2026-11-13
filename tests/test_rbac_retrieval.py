"""Testes de integração do RBAC na busca real (PostgreSQL + pgvector + embeddings).

Não chamam o LLM. Exigem `DATABASE_URL` (banco populado com db/seed.py) e as
demais variáveis do .env; sem isso, os testes são pulados (e pulado não conta
como aprovado).
"""

import os

import pytest
from llama_index.core import QueryBundle
from rbac import Usuario, pode_ver

from conftest import (
    CEO_FUNCIONARIO_ID,
    CEO_HELENA,
    CLIENTE_PAULO,
    GERENTE_MARCOS,
    RH_JULIANA,
    TI_RODRIGO,
    VENDEDOR_CARLOS,
    VENDEDOR_RAFAEL,
)

pytestmark = pytest.mark.integration

if not os.getenv("DATABASE_URL"):
    # O main.py carrega o .env ao ser importado; checamos depois do import.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

PERGUNTAS = [
    "Qual o salário do CEO?",
    "Quanto ganha a Helena Vasconcelos?",
    "Qual o salário do Carlos Lima?",
    "Quais os salários dos funcionários?",
    "Quanto o Rafael Martins vendeu?",
    "Quais vendas a Ana Souza fez?",
    "Quais produtos da categoria Redes temos?",
    "Quem trabalha na região Norte?",
    "Mostre as vendas do MacBook Air M1",
]


@pytest.fixture(scope="module")
def index():
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL não configurada")

    import main

    return main.build_or_load_index()


def buscar(index, usuario: Usuario, pergunta: str):
    import main

    retriever = main.CatalogAndSalesRetriever(index, usuario)
    return retriever.retrieve(QueryBundle(pergunta))


@pytest.mark.parametrize(
    "usuario",
    [VENDEDOR_CARLOS, VENDEDOR_RAFAEL, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, CEO_HELENA, CLIENTE_PAULO],
    ids=lambda u: u.papel + "-" + u.nome.split()[0],
)
@pytest.mark.parametrize("pergunta", PERGUNTAS)
def test_busca_nunca_devolve_documento_proibido(index, usuario, pergunta) -> None:
    for node in buscar(index, usuario, pergunta):
        assert pode_ver(usuario, node.metadata), (
            f"{usuario.papel} recebeu documento proibido: {node.metadata}"
        )


@pytest.mark.parametrize("usuario", [VENDEDOR_CARLOS, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, CLIENTE_PAULO])
def test_ninguem_alem_do_ceo_recebe_o_salario_do_ceo(index, usuario) -> None:
    for pergunta in ("Qual o salário do CEO?", "Quanto ganha a Helena Vasconcelos?"):
        ids = {n.metadata.get("funcionario_id") for n in buscar(index, usuario, pergunta)}
        assert CEO_FUNCIONARIO_ID not in ids


def test_ceo_recebe_o_proprio_salario(index) -> None:
    resultados = buscar(index, CEO_HELENA, "Qual o salário do CEO Helena Vasconcelos?")

    assert any(n.metadata.get("funcionario_id") == CEO_FUNCIONARIO_ID for n in resultados)


def test_rh_ve_salarios_dos_funcionarios_mas_nao_do_ceo(index) -> None:
    resultados = buscar(index, RH_JULIANA, "Qual o salário do Carlos Lima?")
    ids = {n.metadata.get("funcionario_id") for n in resultados}

    assert "F002" in ids
    assert CEO_FUNCIONARIO_ID not in ids


def test_vendedor_ve_o_proprio_salario_e_nao_o_dos_colegas(index) -> None:
    resultados = buscar(index, VENDEDOR_CARLOS, "Qual o meu salário?")
    ids = {n.metadata.get("funcionario_id") for n in resultados if n.metadata.get("tipo") == "funcionario"}

    assert ids <= {"F002"}
    assert "F002" in ids


def test_vendedor_so_recebe_as_proprias_vendas(index) -> None:
    resultados = buscar(index, VENDEDOR_CARLOS, "Quais vendas o Rafael Martins fez do SSD?")
    vendas = [n for n in resultados if n.metadata.get("tipo") == "venda"]

    assert all(n.metadata.get("dono") == "F002" for n in vendas)


def test_gerente_recebe_vendas_de_todos(index) -> None:
    resultados = buscar(index, GERENTE_MARCOS, "Quais vendas do MacBook Air M1 foram feitas?")
    donos = {n.metadata.get("dono") for n in resultados if n.metadata.get("tipo") == "venda"}

    assert len(donos) >= 1
    assert None not in donos


def test_cliente_so_recebe_produtos(index) -> None:
    for pergunta in PERGUNTAS:
        tipos = {n.metadata.get("tipo") for n in buscar(index, CLIENTE_PAULO, pergunta)}
        assert tipos <= {"produto"}, f"cliente recebeu {tipos} em: {pergunta}"


def test_ti_nao_recebe_vendas_nem_salarios(index) -> None:
    for pergunta in PERGUNTAS:
        tipos = {n.metadata.get("tipo") for n in buscar(index, TI_RODRIGO, pergunta)}
        assert tipos <= {"produto", "vendedor", "funcionario"}
        for n in buscar(index, TI_RODRIGO, pergunta):
            if n.metadata.get("tipo") == "funcionario":
                assert n.metadata.get("funcionario_id") == "F013"


def test_login_com_conta_fake_e_senha_errada_falha() -> None:
    if not os.getenv("DATABASE_URL"):
        pytest.skip("DATABASE_URL não configurada")

    import main

    assert main.authenticate("carlos.lima@loja-exemplo.com.br", "demo123") is not None
    assert main.authenticate("carlos.lima@loja-exemplo.com.br", "errada") is None
    assert main.authenticate("nao.existe@loja-exemplo.com.br", "demo123") is None
    assert main.authenticate("' OR '1'='1", "qualquer") is None
