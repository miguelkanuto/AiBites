"""Testes unitários do roteador de modelos."""

import pytest
from router import route, smalltalk_reply


@pytest.mark.parametrize(
    "mensagem",
    ["Oi", "oi!", "Olá, tudo bem?", "bom dia", "Boa tarde, pessoal", "obrigado", "Obrigada!", "valeu", "tchau", "ok"],
)
def test_cumprimentos_vao_para_resposta_pronta(mensagem: str) -> None:
    decisao = route(mensagem)

    assert decisao.name == "smalltalk"
    assert decisao.tier == "none"


@pytest.mark.parametrize(
    "mensagem",
    [
        "Quero pedir férias de 14 a 23 de dezembro",
        "Quantos dias de férias eu tenho?",
        "Abre um ticket pro TI: meu notebook não liga",
        "Qual o status do meu chamado TI-1001?",
        "Manda uma mensagem no canal #vendas avisando da reunião",
        "Envie um aviso no slack",
        "Quanto o Carlos vendeu em outubro?",
        "Qual o total vendido de Informática?",
        "Quem são os 3 melhores vendedores?",
        "Faça um ranking de vendedores",
        "Quantas vendas foram feitas em março?",
        "Qual o faturamento da região Sul?",
    ],
)
def test_acoes_e_contas_exatas_vao_para_o_agente(mensagem: str) -> None:
    decisao = route(mensagem)

    assert decisao.name == "agent"
    assert decisao.tier == "strong"


@pytest.mark.parametrize(
    "mensagem",
    [
        "Qual valor do notebook Dell?",
        "Quais produtos da categoria Redes temos?",
        "Quem trabalha na região Norte?",
        "Quais impressoras vocês vendem?",
        "Qual o meu salário?",
        "Mostre as vendas do MacBook Air M1",
        "Quem é você?",
        "Qual o estoque do Mouse Logitech M170?",
    ],
)
def test_consultas_a_base_vao_para_o_rag(mensagem: str) -> None:
    decisao = route(mensagem)

    assert decisao.name == "rag"
    assert decisao.tier == "standard"


def test_resposta_a_uma_pergunta_do_agente_continua_no_agente() -> None:
    assert route("Notebook não liga desde ontem", continuing_agent=True).name == "agent"
    assert route("de 14 a 23 de dezembro", continuing_agent=True).name == "agent"


def test_agradecimento_encerra_a_continuacao() -> None:
    assert route("obrigado", continuing_agent=True).name == "smalltalk"


@pytest.mark.parametrize(
    "mensagem",
    ["oi, quanto vendi?", "Olá, qual o preço do notebook Dell?", "bom dia, quero pedir férias", "obrigado, mas quanto vendi?"],
)
def test_cumprimento_seguido_de_pergunta_nao_e_conversa_fiada(mensagem: str) -> None:
    assert route(mensagem).name != "smalltalk"


def test_resposta_pronta_usa_o_primeiro_nome() -> None:
    assert "Carlos" in smalltalk_reply("oi", "Carlos")
    assert "De nada" in smalltalk_reply("obrigado", "Carlos")
    assert smalltalk_reply("tchau", "Carlos") == "Até mais!"
