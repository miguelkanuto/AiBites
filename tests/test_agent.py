"""Testes unitários do agente com modelo e servidores falsos (sem rede, sem banco)."""

import asyncio
import json
from types import SimpleNamespace

import ctx_token
import pytest
from agent import MAX_STEPS, MAX_WRITES_PER_TURN, ToolEvent, build_system_prompt, run_agent, to_api_tools
from llm import ChatResult, Tier
from mcp_hub import ToolInfo

from conftest import CEO_HELENA, CLIENTE_PAULO, GERENTE_MARCOS, VENDEDOR_CARLOS

TIER = Tier("strong", "modelo-falso", 3.0, 15.0)


def info(nome: str, props: dict | None = None) -> ToolInfo:
    servidor, _, ferramenta = nome.partition(".")
    return ToolInfo(nome, servidor, ferramenta, f"descrição de {nome}", {"type": "object", "properties": props or {}})


CATALOGO = [
    info("rh.solicitar_ferias", {"data_inicio": {"type": "string"}, "data_fim": {"type": "string"}}),
    info("ti.abrir_ticket", {"titulo": {"type": "string"}}),
    info("slack.enviar_mensagem", {"canal": {"type": "string"}, "texto": {"type": "string"}}),
    info("vendas.total_vendido"),
    info("vendas.ranking_vendedores"),
]


class FakeHub:
    def __init__(self, resposta: str = '{"ok": true}') -> None:
        self.chamadas: list[tuple[str, dict, str]] = []
        self.resposta = resposta

    def catalog(self) -> list[ToolInfo]:
        return CATALOGO

    async def call(self, nome: str, argumentos: dict, token: str) -> tuple[str, bool]:
        self.chamadas.append((nome, argumentos, token))
        return self.resposta, False


class FakeHooks:
    def __init__(self, confirma: bool = True) -> None:
        self.confirma = confirma
        self.resumos: list[str] = []
        self.eventos: list[ToolEvent] = []

    async def confirm(self, resumo: str) -> bool:
        self.resumos.append(resumo)
        return self.confirma

    async def on_tool(self, evento: ToolEvent) -> None:
        self.eventos.append(evento)


def chamada(nome: str, argumentos: dict | str, id_: str = "c1"):
    texto = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=nome, arguments=texto))


def resposta(texto: str = "", chamadas: list | None = None, tokens: tuple[int, int] = (100, 20)) -> ChatResult:
    mensagem = SimpleNamespace(content=texto, tool_calls=chamadas or None)
    return ChatResult(message=mensagem, tier=TIER, prompt_tokens=tokens[0], completion_tokens=tokens[1], cost=0.001)


def roteiro(*respostas: ChatResult):
    fila = list(respostas)
    chamadas_ao_modelo: list[dict] = []

    async def chat_fn(tier, messages, **kwargs):
        chamadas_ao_modelo.append({"messages": list(messages), **kwargs})
        return fila.pop(0) if len(fila) > 1 else fila[0]

    chat_fn.historico = chamadas_ao_modelo  # type: ignore[attr-defined]
    return chat_fn


@pytest.fixture(autouse=True)
def segredo(monkeypatch):
    monkeypatch.setenv("MCP_CONTEXT_SECRET", "segredo-de-teste")


def rodar(pergunta, usuario, hub, hooks, chat_fn):
    return asyncio.run(run_agent(pergunta, usuario, hub, hooks, chat_fn=chat_fn))


# --- Ferramentas visíveis ---


def test_modelo_so_ve_as_ferramentas_do_papel() -> None:
    ferramentas, mapa = to_api_tools(CATALOGO, "vendedor")

    nomes = {f["function"]["name"] for f in ferramentas}
    assert "vendas__ranking_vendedores" not in nomes
    assert {"rh__solicitar_ferias", "ti__abrir_ticket", "vendas__total_vendido"} <= nomes
    assert set(mapa) == nomes


def test_gerente_ve_o_ranking_e_cliente_nao_ve_nada() -> None:
    assert "vendas__ranking_vendedores" in {f["function"]["name"] for f in to_api_tools(CATALOGO, "gerente_vendas")[0]}
    assert to_api_tools(CATALOGO, "cliente")[0] == []


def test_prompt_do_agente_traz_data_e_usuario() -> None:
    prompt = build_system_prompt(CEO_HELENA)

    assert "Helena Vasconcelos" in prompt and "ceo" in prompt
    assert "AAAA-MM-DD" in prompt


# --- Fluxo ---


def test_resposta_direta_sem_ferramenta() -> None:
    chat_fn = roteiro(resposta("Olá! Posso ajudar com férias e tickets."))

    resultado = rodar("oi", VENDEDOR_CARLOS, FakeHub(), FakeHooks(), chat_fn)

    assert resultado.answer.startswith("Olá")
    assert resultado.events == []
    assert resultado.steps == 1


def test_consulta_executa_a_ferramenta_e_responde_com_o_resultado() -> None:
    hub = FakeHub('{"ok": true, "total_vendido": 21899.3}')
    chat_fn = roteiro(
        resposta(chamadas=[chamada("vendas__total_vendido", {"categoria": "Informática"})]),
        resposta("Você vendeu R$ 21.899,30."),
    )

    resultado = rodar("quanto vendi?", VENDEDOR_CARLOS, hub, FakeHooks(), chat_fn)

    assert resultado.answer == "Você vendeu R$ 21.899,30."
    assert [e.status for e in resultado.events] == ["ok"]
    assert hub.chamadas[0][0] == "vendas.total_vendido"
    assert resultado.steps == 2
    assert resultado.cost == pytest.approx(0.002)
    assert resultado.prompt_tokens == 200


def test_contexto_injetado_e_do_usuario_logado_nao_do_modelo() -> None:
    hub = FakeHub()
    forjado = {"categoria": "Software", "contexto": "token-forjado-pelo-modelo", "funcionario_id": "F014"}
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__total_vendido", forjado)]), resposta("ok"))

    rodar("quanto vendi?", VENDEDOR_CARLOS, hub, FakeHooks(), chat_fn)

    _, argumentos, token = hub.chamadas[0]
    assert ctx_token.verify(token) == VENDEDOR_CARLOS
    assert token != "token-forjado-pelo-modelo"


def test_ferramenta_fora_da_politica_nunca_chega_ao_servidor() -> None:
    hub = FakeHub()
    hooks = FakeHooks()
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__ranking_vendedores", {"top": 3})]), resposta("Não posso."))

    resultado = rodar("ranking", VENDEDOR_CARLOS, hub, hooks, chat_fn)

    assert hub.chamadas == []
    assert resultado.events[0].status == "negado"
    assert hooks.resumos == []


def test_ferramenta_inventada_e_negada() -> None:
    hub = FakeHub()
    chat_fn = roteiro(resposta(chamadas=[chamada("sistema__apagar_tudo", {})]), resposta("ok"))

    resultado = rodar("faça", CEO_HELENA, hub, FakeHooks(), chat_fn)

    assert hub.chamadas == []
    assert resultado.events[0].status == "negado"


def test_cliente_nao_executa_nada_mesmo_que_o_modelo_tente() -> None:
    hub = FakeHub()
    chat_fn = roteiro(resposta(chamadas=[chamada("rh__solicitar_ferias", {"data_inicio": "2026-12-14", "data_fim": "2026-12-23"})]), resposta("ok"))

    resultado = rodar("férias", CLIENTE_PAULO, hub, FakeHooks(), chat_fn)

    assert hub.chamadas == []
    assert resultado.events[0].status == "negado"


# --- Confirmação ---


def test_acao_que_altera_pede_confirmacao_e_executa_se_confirmada() -> None:
    hub = FakeHub('{"ok": true, "protocolo": "FER-2026-0001"}')
    hooks = FakeHooks(confirma=True)
    args = {"data_inicio": "2026-12-14", "data_fim": "2026-12-23"}
    chat_fn = roteiro(resposta(chamadas=[chamada("rh__solicitar_ferias", args)]), resposta("Registrado."))

    resultado = rodar("férias", VENDEDOR_CARLOS, hub, hooks, chat_fn)

    assert len(hooks.resumos) == 1 and "2026-12-14" in hooks.resumos[0]
    assert hub.chamadas[0][0] == "rh.solicitar_ferias"
    assert resultado.events[0].status == "ok" and resultado.events[0].confirmed is True


def test_acao_cancelada_pelo_usuario_nao_executa() -> None:
    hub = FakeHub()
    hooks = FakeHooks(confirma=False)
    chat_fn = roteiro(
        resposta(chamadas=[chamada("slack__enviar_mensagem", {"canal": "#vendas", "texto": "reunião às 15h"})]),
        resposta("Cancelado."),
    )

    resultado = rodar("manda no vendas", VENDEDOR_CARLOS, hub, hooks, chat_fn)

    assert hub.chamadas == []
    assert resultado.events[0].status == "cancelado"
    assert resultado.events[0].confirmed is False


def test_consulta_nao_pede_confirmacao() -> None:
    hooks = FakeHooks()
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__total_vendido", {})]), resposta("ok"))

    rodar("quanto?", VENDEDOR_CARLOS, FakeHub(), hooks, chat_fn)

    assert hooks.resumos == []


def test_limite_de_acoes_que_alteram_por_mensagem() -> None:
    hub = FakeHub()
    chamadas = [chamada("ti__abrir_ticket", {"titulo": f"Chamado {i}"}, id_=f"c{i}") for i in range(MAX_WRITES_PER_TURN + 2)]
    chat_fn = roteiro(resposta(chamadas=chamadas), resposta("feito"))

    resultado = rodar("abra vários", VENDEDOR_CARLOS, hub, FakeHooks(), chat_fn)

    status = [e.status for e in resultado.events]
    assert status.count("ok") == MAX_WRITES_PER_TURN
    assert status.count("negado") == 2
    assert len(hub.chamadas) == MAX_WRITES_PER_TURN


# --- Robustez ---


def test_argumentos_malformados_viram_erro_sem_chamar_o_servidor() -> None:
    hub = FakeHub()
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__total_vendido", "{isso nao e json")]), resposta("ok"))

    resultado = rodar("quanto?", VENDEDOR_CARLOS, hub, FakeHooks(), chat_fn)

    assert hub.chamadas == []
    assert resultado.events[0].status == "erro"


def test_erro_de_negocio_da_ferramenta_e_marcado_como_erro() -> None:
    hub = FakeHub('{"ok": false, "erro": "Saldo insuficiente"}')
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__total_vendido", {})]), resposta("Não deu."))

    resultado = rodar("quanto?", VENDEDOR_CARLOS, hub, FakeHooks(), chat_fn)

    assert resultado.events[0].status == "erro"


def test_laco_infinito_e_interrompido() -> None:
    chat_fn = roteiro(resposta(chamadas=[chamada("vendas__total_vendido", {})]))

    resultado = rodar("quanto?", VENDEDOR_CARLOS, FakeHub(), FakeHooks(), chat_fn)

    assert resultado.steps == MAX_STEPS
    assert "reformular" in resultado.answer


def test_resultado_da_ferramenta_vai_ao_modelo_como_mensagem_de_ferramenta() -> None:
    chat_fn = roteiro(
        resposta(chamadas=[chamada("vendas__total_vendido", {}, id_="abc")]),
        resposta("pronto"),
    )

    rodar("quanto?", VENDEDOR_CARLOS, FakeHub('{"ok": true}'), FakeHooks(), chat_fn)

    segunda = chat_fn.historico[1]["messages"]  # type: ignore[attr-defined]
    assert segunda[-1] == {"role": "tool", "tool_call_id": "abc", "content": '{"ok": true}'}
    assert segunda[-2]["tool_calls"][0]["function"]["name"] == "vendas__total_vendido"
