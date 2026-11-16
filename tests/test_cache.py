"""Testes do cache semântico: regras puras e uso no banco com vetores montados à mão."""

import os

import pytest
from cache import is_cacheable, lookup, scope_key, store
from sqlalchemy import text

# --- Regras puras ---


def test_escopo_depende_dos_niveis_do_papel() -> None:
    assert scope_key("cliente") == "publico"
    assert scope_key("vendedor") == scope_key("ti") == "interno,publico"
    assert scope_key("gerente_vendas") != scope_key("vendedor")
    assert scope_key("ceo") != scope_key("rh")
    assert scope_key("papel-inexistente") == "nenhum"


def test_resposta_com_documentos_visiveis_pelo_nivel_pode_ser_guardada() -> None:
    fontes = [{"nivel": "publico"}, {"nivel": "interno"}]

    assert is_cacheable("Quais impressoras vocês vendem?", fontes, "HP DeskJet e Epson", "vendedor") is True
    assert is_cacheable("Quais impressoras vocês vendem?", fontes, "HP DeskJet e Epson", "cliente") is False  # interno


def test_gerente_e_ceo_guardam_respostas_com_documentos_do_nivel_deles() -> None:
    assert is_cacheable("Quais vendas do MacBook?", [{"nivel": "vendas", "dono": "F002"}], "r", "gerente_vendas") is True
    assert is_cacheable("Quanto ganha o CEO?", [{"nivel": "diretoria", "dono": "F014"}], "r", "ceo") is True


@pytest.mark.parametrize(
    ("papel", "fontes"),
    [
        ("vendedor", [{"nivel": "publico"}, {"nivel": "vendas", "dono": "F002"}]),  # só visível por ser dele
        ("vendedor", [{"nivel": "rh", "dono": "F002"}]),
        ("gerente_vendas", [{"nivel": "rh", "dono": "F011"}]),
        ("rh", [{"nivel": "diretoria", "dono": "F014"}]),
        ("cliente", [{"nivel": "interno"}]),
        ("vendedor", [{"nivel": "vendas"}]),
        ("vendedor", []),
        ("papel-inexistente", [{"nivel": "publico"}]),
    ],
)
def test_nunca_guarda_o_que_so_apareceu_por_ser_do_proprio_usuario(papel: str, fontes) -> None:
    assert is_cacheable("Quais produtos temos?", fontes, "resposta", papel) is False


@pytest.mark.parametrize("pergunta", ["Qual o meu salário?", "Quais foram as minhas vendas?", "o que eu posso ver?"])
def test_pergunta_na_primeira_pessoa_nao_entra_no_cache(pergunta: str) -> None:
    assert is_cacheable(pergunta, [{"nivel": "publico"}], "resposta", "ceo") is False


def test_resposta_vazia_nao_entra() -> None:
    assert is_cacheable("Quais produtos?", [{"nivel": "publico"}], "   ", "ceo") is False


# --- Banco (integração) ---

TESTE = "TESTE-CACHE"
VERSAO = "versao-de-teste"


def _vetor(*primeiros: float) -> list[float]:
    return [*primeiros, *([0.0] * (384 - len(primeiros)))]


@pytest.fixture
def engine():
    if not os.getenv("AIBITES_DATABASE_URL") or not os.getenv("AIBITES_ADMIN_DATABASE_URL"):
        pytest.skip("Precisa de AIBITES_DATABASE_URL e AIBITES_ADMIN_DATABASE_URL")

    import main

    yield main.get_engine()

    with main.get_admin_engine().begin() as connection:
        connection.execute(text("DELETE FROM cache_semantico WHERE versao_indice = :v"), {"v": VERSAO})


@pytest.mark.integration
def test_pergunta_parecida_acerta_o_cache(engine) -> None:
    store(engine, _vetor(1.0, 0.0), "publico", VERSAO, "quais impressoras vocês vendem?", "HP e Epson")

    acerto = lookup(engine, _vetor(0.99, 0.05), "publico", VERSAO)

    assert acerto is not None
    assert acerto.answer == "HP e Epson"
    assert acerto.similarity > 0.92


@pytest.mark.integration
def test_pergunta_diferente_nao_acerta(engine) -> None:
    store(engine, _vetor(1.0, 0.0), "publico", VERSAO, "impressoras", "HP e Epson")

    assert lookup(engine, _vetor(0.0, 1.0), "publico", VERSAO) is None


@pytest.mark.integration
def test_escopo_diferente_nao_acerta(engine) -> None:
    store(engine, _vetor(1.0), "interno,publico", VERSAO, "p", "resposta de funcionário")

    assert lookup(engine, _vetor(1.0), "publico", VERSAO) is None
    assert lookup(engine, _vetor(1.0), "interno,publico", VERSAO) is not None


@pytest.mark.integration
def test_versao_diferente_dos_dados_invalida_o_cache(engine) -> None:
    store(engine, _vetor(1.0), "publico", VERSAO, "p", "resposta antiga")

    assert lookup(engine, _vetor(1.0), "publico", "outra-versao") is None


@pytest.mark.integration
def test_entrada_vencida_nao_e_servida(engine) -> None:
    store(engine, _vetor(1.0), "publico", VERSAO, "p", "vencida", ttl_hours=-1)

    assert lookup(engine, _vetor(1.0), "publico", VERSAO) is None


@pytest.mark.integration
def test_acertos_sao_contados(engine) -> None:
    store(engine, _vetor(1.0), "publico", VERSAO, "p", "resposta")
    lookup(engine, _vetor(1.0), "publico", VERSAO)
    lookup(engine, _vetor(1.0), "publico", VERSAO)

    with engine.connect() as connection:
        acertos = connection.execute(
            text("SELECT acertos FROM cache_semantico WHERE versao_indice = :v"), {"v": VERSAO}
        ).scalar_one()

    assert acertos == 2
