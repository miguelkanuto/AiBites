"""Parte offline dos casos de avaliação (evals/casos.json): sem rede, sem LLM, roda no CI.

A avaliação completa (evals/run.py) chama o modelo de verdade; aqui só se garante que o arquivo
de casos é coerente e que as regras determinísticas (roteador e guardrail) concordam com ele.
"""

import json
from pathlib import Path

import pytest
from guardrails import check_input
from personas import BY_ID
from router import route

DADOS = json.loads((Path(__file__).resolve().parent.parent / "evals" / "casos.json").read_text(encoding="utf-8"))
CASOS = DADOS["casos"]
CHAVES = {
    "rota", "bloqueada", "confirmacao", "resposta_nao_contem", "resposta_contem_qualquer", "fontes_nao_contem",
    "fontes_nao_prefixo", "fontes_contem_prefixo", "ferramentas_contem", "ferramentas_nao",
}


def test_ids_unicos_e_personas_existentes():
    ids = [c["id"] for c in CASOS]
    assert len(ids) == len(set(ids))
    assert all(c["persona"] in BY_ID for c in CASOS)


def test_toda_categoria_tem_limiar_e_chaves_validas():
    assert {c["categoria"] for c in CASOS} <= set(DADOS["limiares"])
    for caso in CASOS:
        assert caso["espera"], caso["id"]
        assert set(caso["espera"]) <= CHAVES, caso["id"]


@pytest.mark.parametrize("caso", [c for c in CASOS if "rota" in c["espera"]], ids=lambda c: c["id"])
def test_roteador_concorda_com_o_caso(caso):
    assert route(caso["pergunta"]).name == caso["espera"]["rota"]


@pytest.mark.parametrize("caso", [c for c in CASOS if c["espera"].get("bloqueada")], ids=lambda c: c["id"])
def test_ataques_do_caso_ao_menos_acendem_o_guardrail(caso):
    # Na zona cinzenta quem decide é o modelo juiz (online); offline basta o filtro marcar como suspeito.
    veredito = check_input(caso["pergunta"])
    assert veredito.suspicious or not veredito.allowed
