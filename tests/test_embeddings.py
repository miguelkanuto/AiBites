"""Testes do cliente de embeddings do Gemini. Nenhum chama a rede: usam transporte simulado."""

import json
import math

import httpx
import pytest

import embeddings
from embeddings import EmbeddingError, GeminiEmbedding, normalize

CHAVE = "AIzaChaveDeTesteNaoReal123"
DIM = 8


def _vetor(seed: float) -> list[float]:
    return [seed + i for i in range(DIM)]


def _modelo(handler, **kwargs) -> tuple[GeminiEmbedding, list[httpx.Request]]:
    chamadas: list[httpx.Request] = []

    def envolver(request: httpx.Request) -> httpx.Response:
        chamadas.append(request)
        return handler(request)

    cliente = httpx.Client(transport=httpx.MockTransport(envolver))
    return GeminiEmbedding(model_name="gemini-embedding-001", dim=DIM, api_key=CHAVE, client=cliente, **kwargs), chamadas


def _ok(request: httpx.Request) -> httpx.Response:
    pedidos = json.loads(request.content)["requests"]
    return httpx.Response(200, json={"embeddings": [{"values": _vetor(float(i + 1))} for i, _ in enumerate(pedidos)]})


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    esperas: list[float] = []
    monkeypatch.setattr(embeddings, "_sleep", esperas.append)
    return esperas


def test_normalize_gera_norma_um():
    vetor = normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in vetor)), 1.0)


def test_normalize_vetor_zero_nao_quebra():
    assert normalize([0.0, 0.0]) == [0.0, 0.0]


def test_consulta_usa_tipo_de_consulta_dimensao_e_chave_no_cabecalho():
    modelo, chamadas = _modelo(_ok)
    vetor = modelo.get_query_embedding("Quais impressoras vocês vendem?")

    assert len(chamadas) == 1
    pedido = chamadas[0]
    assert pedido.headers["x-goog-api-key"] == CHAVE
    assert CHAVE not in str(pedido.url)
    corpo = json.loads(pedido.content)["requests"][0]
    assert corpo["taskType"] == "RETRIEVAL_QUERY"
    assert corpo["outputDimensionality"] == DIM
    assert corpo["model"] == "models/gemini-embedding-001"
    assert math.isclose(math.sqrt(sum(x * x for x in vetor)), 1.0, rel_tol=1e-9)
    assert len(vetor) == DIM


def test_documento_usa_tipo_de_documento():
    modelo, chamadas = _modelo(_ok)
    modelo.get_text_embedding("Notebook Dell Inspiron")
    assert json.loads(chamadas[0].content)["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"


def test_lote_grande_e_dividido_em_chamadas_de_100():
    modelo, chamadas = _modelo(_ok)
    textos = [f"documento {i}" for i in range(250)]
    vetores = modelo._get_text_embeddings(textos)

    assert len(vetores) == 250
    assert [len(json.loads(c.content)["requests"]) for c in chamadas] == [100, 100, 50]


def test_mesma_consulta_repetida_so_chama_a_api_uma_vez():
    modelo, chamadas = _modelo(_ok)
    primeiro = modelo.get_query_embedding("qual o preço do iPhone 15?")
    segundo = modelo.get_query_embedding("qual o preço do iPhone 15?")
    assert primeiro == segundo
    assert len(chamadas) == 1


def test_resultado_do_cache_nao_pode_ser_alterado_por_quem_recebe():
    modelo, _ = _modelo(_ok)
    primeiro = modelo.get_query_embedding("teste")
    primeiro[0] = 999.0
    assert modelo.get_query_embedding("teste")[0] != 999.0


def test_tenta_de_novo_quando_a_cota_acaba_e_depois_funciona(sem_espera):
    respostas = iter([httpx.Response(429), httpx.Response(503), None])

    def handler(request):
        resposta = next(respostas)
        return resposta if resposta is not None else _ok(request)

    modelo, chamadas = _modelo(handler)
    modelo.get_query_embedding("oi")
    assert len(chamadas) == 3
    assert sem_espera == [2.0, 4.0]


def test_respeita_retry_after_do_provedor(sem_espera):
    respostas = iter([httpx.Response(429, headers={"retry-after": "7"}), None])

    def handler(request):
        resposta = next(respostas)
        return resposta if resposta is not None else _ok(request)

    modelo, _ = _modelo(handler)
    modelo.get_query_embedding("oi")
    assert sem_espera == [7.0]


def test_desiste_sem_vazar_a_chave_quando_a_cota_nao_volta():
    modelo, chamadas = _modelo(lambda request: httpx.Response(429))
    with pytest.raises(EmbeddingError) as erro:
        modelo.get_query_embedding("oi")
    assert CHAVE not in str(erro.value)
    assert "429" in str(erro.value)
    assert len(chamadas) < 10


def test_erro_do_cliente_nao_tenta_de_novo_e_nao_vaza_a_chave():
    modelo, chamadas = _modelo(lambda request: httpx.Response(400, text=f"chave inválida {CHAVE}"))
    with pytest.raises(EmbeddingError) as erro:
        modelo.get_query_embedding("oi")
    assert len(chamadas) == 1
    assert CHAVE not in str(erro.value)
    assert "400" in str(erro.value)


def test_falha_de_rede_vira_erro_sem_url_nem_chave():
    def handler(request):
        raise httpx.ConnectError(f"falha ao conectar em {request.url}")

    modelo, _ = _modelo(handler)
    with pytest.raises(EmbeddingError) as erro:
        modelo.get_query_embedding("oi")
    assert CHAVE not in str(erro.value)
    assert "googleapis" not in str(erro.value)


def test_vetor_com_tamanho_errado_e_rejeitado():
    modelo, _ = _modelo(lambda request: httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2]}]}))
    with pytest.raises(EmbeddingError):
        modelo.get_query_embedding("oi")


def test_resposta_com_quantidade_errada_e_rejeitada():
    modelo, _ = _modelo(lambda request: httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(EmbeddingError):
        modelo.get_query_embedding("oi")


def test_sem_chave_o_erro_e_claro(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(EmbeddingError, match="GEMINI_API_KEY"):
        GeminiEmbedding(dim=DIM)
