"""Testes unitários do parecer do juiz e das contas de custo simulado."""

import pytest
from judge import parse_judge_output
from llm import Tier, estimate_cost, get_tiers, reference_cost
from mcp_hub import public_schema


@pytest.mark.parametrize(
    ("bruto", "ataque"),
    [
        ('{"ataque": true, "motivo": "pede para ignorar regras"}', True),
        ('{"ataque": false, "motivo": "pergunta normal"}', False),
        ('```json\n{"ataque": true, "motivo": "x"}\n```', True),
        ('Claro! Aqui está: {"ataque": false, "motivo": "ok"} espero ter ajudado', False),
        ('{"ataque": "sim", "motivo": "x"}', True),
        ('{"ataque": "false", "motivo": "x"}', False),
    ],
)
def test_juiz_le_respostas_em_varios_formatos(bruto: str, ataque: bool) -> None:
    resultado = parse_judge_output(bruto)

    assert resultado.available is True
    assert resultado.attack is ataque


@pytest.mark.parametrize("bruto", ["", "sem json aqui", "{quebrado", '{"outro": 1}', '{"ataque": 3}'])
def test_resposta_ilegivel_do_juiz_nao_vale_e_nao_bloqueia(bruto: str) -> None:
    resultado = parse_judge_output(bruto)

    assert resultado.available is False
    assert resultado.attack is False


def test_custo_simulado_segue_o_preco_por_milhao_de_tokens() -> None:
    faixa = Tier("x", "modelo", input_price=2.0, output_price=10.0)

    assert estimate_cost(faixa, 1_000_000, 0) == pytest.approx(2.0)
    assert estimate_cost(faixa, 0, 1_000_000) == pytest.approx(10.0)
    assert estimate_cost(faixa, 500, 100) == pytest.approx(0.002)


def test_faixas_ficam_mais_caras_da_leve_para_a_forte() -> None:
    faixas = get_tiers()

    assert faixas["light"].input_price < faixas["standard"].input_price < faixas["strong"].input_price
    assert faixas["light"].output_price < faixas["standard"].output_price < faixas["strong"].output_price


def test_referencia_e_o_custo_na_faixa_forte() -> None:
    assert reference_cost(1000, 200) == pytest.approx(estimate_cost(get_tiers()["strong"], 1000, 200))
    assert reference_cost(1000, 200) > estimate_cost(get_tiers()["standard"], 1000, 200)


def test_faixa_pode_ser_trocada_por_variavel_de_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_MODEL_STRONG", "outro/modelo:free")

    assert get_tiers()["strong"].model == "outro/modelo:free"


def test_schema_publico_nao_tem_o_contexto() -> None:
    schema = {
        "type": "object",
        "title": "x",
        "properties": {"contexto": {"type": "string"}, "titulo": {"type": "string"}},
        "required": ["contexto", "titulo"],
    }

    publico = public_schema(schema)

    assert set(publico["properties"]) == {"titulo"}
    assert publico["required"] == ["titulo"]
    assert "title" not in publico


def test_schema_publico_sem_obrigatorios_remove_required() -> None:
    publico = public_schema({"type": "object", "properties": {"contexto": {}}, "required": ["contexto"]})

    assert "required" not in publico and publico["properties"] == {}
