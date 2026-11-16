"""Testes unitários da política de ferramentas e do contexto assinado."""

import base64
import os

import pytest
from ctx_token import MAX_AGE_SECONDS, ContextoInvalido, sign, verify
from tool_policy import (
    CANAIS,
    FERRAMENTAS,
    canais_permitidos,
    exige_confirmacao,
    ferramentas_permitidas,
    pode_usar,
    resumir,
)

from conftest import CEO_HELENA, CLIENTE_PAULO, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, VENDEDOR_CARLOS


@pytest.fixture(autouse=True)
def segredo(monkeypatch):
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "segredo-de-teste")


# --- Política ---


def test_cliente_nao_tem_nenhuma_ferramenta() -> None:
    assert ferramentas_permitidas("cliente") == []


def test_papel_desconhecido_nao_tem_ferramentas() -> None:
    assert ferramentas_permitidas("administrador") == []
    assert pode_usar("administrador", "rh.consultar_saldo_ferias") is False


def test_ferramenta_inexistente_e_negada() -> None:
    assert pode_usar("ceo", "rh.apagar_tudo") is False


@pytest.mark.parametrize(
    ("papel", "ferramenta", "esperado"),
    [
        ("vendedor", "rh.solicitar_ferias", True),
        ("vendedor", "ti.abrir_ticket", True),
        ("vendedor", "ti.listar_fila", False),
        ("vendedor", "vendas.ranking_vendedores", False),
        ("vendedor", "vendas.total_vendido", True),
        ("ti", "ti.listar_fila", True),
        ("ti", "vendas.total_vendido", False),
        ("rh", "vendas.total_vendido", False),
        ("gerente_vendas", "vendas.ranking_vendedores", True),
        ("ceo", "ti.listar_fila", True),
    ],
)
def test_matriz_de_ferramentas_por_papel(papel: str, ferramenta: str, esperado: bool) -> None:
    assert pode_usar(papel, ferramenta) is esperado


def test_acoes_que_alteram_algo_exigem_confirmacao() -> None:
    escrevem = {nome for nome, politica in FERRAMENTAS.items() if politica.escreve}

    assert escrevem == {"rh.solicitar_ferias", "ti.abrir_ticket", "slack.enviar_mensagem"}
    assert all(exige_confirmacao(nome) for nome in escrevem)
    assert exige_confirmacao("vendas.total_vendido") is False


def test_toda_ferramenta_que_escreve_tem_resumo() -> None:
    for nome, politica in FERRAMENTAS.items():
        if politica.escreve:
            assert politica.resumo, nome


def test_resumo_preenche_os_argumentos_e_marca_o_que_falta() -> None:
    texto = resumir("ti.abrir_ticket", {"titulo": "VPN caiu", "prioridade": "alta"})

    assert "VPN caiu" in texto and "alta" in texto and "?" in texto


def test_canais_por_papel() -> None:
    assert "#diretoria" in canais_permitidos("ceo")
    assert "#diretoria" not in canais_permitidos("vendedor")
    assert "#vendas" not in canais_permitidos("ti")
    assert canais_permitidos("cliente") == []
    assert set(CANAIS) >= {"#geral", "#vendas", "#ti", "#rh", "#diretoria"}


# --- Contexto assinado ---


def test_contexto_assinado_volta_igual() -> None:
    usuario = verify(sign(CEO_HELENA))

    assert usuario == CEO_HELENA


@pytest.mark.parametrize("usuario", [VENDEDOR_CARLOS, GERENTE_MARCOS, RH_JULIANA, TI_RODRIGO, CLIENTE_PAULO])
def test_contexto_preserva_papel_e_ids(usuario) -> None:
    recebido = verify(sign(usuario))

    assert (recebido.papel, recebido.funcionario_id, recebido.cliente_id) == (
        usuario.papel,
        usuario.funcionario_id,
        usuario.cliente_id,
    )


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "abc.def", "."])
def test_contexto_malformado_e_recusado(token: str) -> None:
    with pytest.raises(ContextoInvalido):
        verify(token)


def test_contexto_com_papel_adulterado_e_recusado() -> None:
    payload, assinatura = sign(VENDEDOR_CARLOS).split(".")
    original = base64.urlsafe_b64decode(payload + "==")
    forjado = original.replace(b'"vendedor"', b'"ceo"    ')
    token = base64.urlsafe_b64encode(forjado).decode().rstrip("=") + "." + assinatura

    with pytest.raises(ContextoInvalido):
        verify(token)


def test_contexto_assinado_com_outro_segredo_e_recusado(monkeypatch) -> None:
    token = sign(VENDEDOR_CARLOS)
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "outro-segredo")

    with pytest.raises(ContextoInvalido):
        verify(token)


def test_contexto_vencido_e_recusado() -> None:
    token = sign(VENDEDOR_CARLOS, now=1000.0)

    assert verify(token, now=1000.0 + MAX_AGE_SECONDS - 1).papel == "vendedor"
    with pytest.raises(ContextoInvalido):
        verify(token, now=1000.0 + MAX_AGE_SECONDS + 1)


def test_sem_segredo_configurado_nao_assina(monkeypatch) -> None:
    monkeypatch.delenv("MCP_CONTEXT_SECRET", raising=False)
    monkeypatch.delenv("CHAINLIT_AUTH_SECRET", raising=False)

    with pytest.raises(ContextoInvalido):
        sign(VENDEDOR_CARLOS)
    assert "MCP_CONTEXT_SECRET" not in os.environ
