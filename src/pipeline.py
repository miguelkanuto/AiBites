"""Fluxo de uma mensagem, independente da interface (Chainlit ou API do site).

limites e risco → guardrails (regras + juiz leve) → roteador →
(resposta pronta | cache + RAG | agente com ferramentas) → filtro de saída → auditoria.

A interface só fornece o usuário, o estado da conversa e os `hooks` (confirmação
e exibição de ferramentas). Tudo o que protege ou custa dinheiro mora aqui, para
valer igual em qualquer interface.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from agent import AgentHooks, ToolEvent, run_agent
from audit import log_conversation, log_event, log_tool_call
from cache import is_cacheable
from cache import lookup as cache_lookup
from cache import scope_key as cache_scope
from cache import store as cache_store
from embeddings import EmbeddingError
from guardrails import BLOCK_THRESHOLD, check_input, leaks_system_prompt, redact
from judge import judge_injection
from limits import risk_paused
from llm import estimate_cost, get_tiers, reference_cost
from rbac import Usuario
from router import route, smalltalk_reply
from tool_policy import ferramentas_permitidas

logger = logging.getLogger(__name__)

MSG_EMBEDDINGS_DOWN = (
    "A busca na base está indisponível agora (o serviço de embeddings atingiu o limite ou não respondeu). "
    "Tente de novo em alguns minutos."
)

NO_TOOLS_MESSAGE = "Essa ação não está disponível para o seu perfil. Posso ajudar a consultar produtos."


@dataclass
class ConversationState:
    """Estado de uma conversa que precisa sobreviver entre mensagens.

    Attributes:
        agent_history: Últimas mensagens trocadas com o agente (para perguntas de esclarecimento).
    """

    agent_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Outcome:
    """Resultado de uma mensagem, com tudo o que a interface pode querer mostrar.

    Attributes:
        answer: Texto final para o usuário.
        route: `smalltalk`, `rag`, `agent` ou `bloqueada`.
        route_reason: Regra do roteador (ou motivo do bloqueio).
        model: Modelo (ou "resposta pronta", "cache semântico").
        cost: Custo simulado em US$.
        reference_cost: Custo simulado se fosse sempre a faixa forte.
        latency_ms: Tempo da etapa de resposta.
        blocked: `True` quando a mensagem foi recusada sem chamar modelo.
        reasons: Motivos de guardrail, limite ou cache.
        risk: Pontuação de risco da mensagem.
        cache_hit: `True` quando veio do cache semântico.
        sources: Documentos usados (`tipo:id`).
        tool_events: Chamadas de ferramenta (agente).
        trace_id: Identificador que liga log, ferramentas e rastro.
        stages: Etapas percorridas, em ordem, para visualização.
    """

    answer: str
    route: str = ""
    route_reason: str = ""
    model: str = ""
    cost: float = 0.0
    reference_cost: float = 0.0
    latency_ms: int = 0
    blocked: bool = False
    reasons: tuple[str, ...] = ()
    risk: int = 0
    cache_hit: bool = False
    sources: list[str] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    trace_id: str = ""
    stages: list[dict[str, Any]] = field(default_factory=list)


class _LoggingHooks:
    """Envolve os hooks da interface e grava cada chamada de ferramenta."""

    def __init__(self, inner: AgentHooks, engine, usuario: Usuario, trace_id: str, events: list[ToolEvent]) -> None:
        self._inner = inner
        self._engine = engine
        self._usuario = usuario
        self._trace_id = trace_id
        self._events = events

    async def confirm(self, summary: str) -> bool:
        return await self._inner.confirm(summary)

    async def on_tool(self, event: ToolEvent) -> None:
        import asyncio

        self._events.append(event)
        await self._inner.on_tool(event)
        await asyncio.to_thread(
            log_tool_call,
            self._engine,
            trace_id=self._trace_id,
            usuario_id=self._usuario.usuario_id,
            papel=self._usuario.papel,
            servidor=event.server,
            ferramenta=event.tool,
            argumentos=event.arguments,
            status=event.status,
            resultado=event.result,
            duracao_ms=event.duration_ms,
            confirmada=event.confirmed,
        )


async def embed_query(core: Any, text: str) -> list[float] | None:
    """Vetor da pergunta, ou `None` quando o provedor de embeddings falha ou está sem cota.

    Só `EmbeddingError` é tratada: qualquer outro erro é bug e deve aparecer.
    """
    import asyncio

    try:
        return await asyncio.to_thread(core.create_embed_model().get_query_embedding, text)
    except EmbeddingError as error:
        logger.warning("Embeddings indisponíveis (cache e busca ignorados): %s", error)
        return None


async def process_message(
    text: str,
    usuario: Usuario,
    state: ConversationState,
    hooks: AgentHooks,
    session_id: str | None = None,
    core: Any = None,
) -> Outcome:
    """Processa uma mensagem do usuário do começo ao fim.

    Args:
        text: Mensagem digitada.
        usuario: Quem pergunta (papel e ids definem tudo o que ele pode ver e fazer).
        state: Estado da conversa (muda aqui dentro).
        hooks: Confirmação de ações e exibição de ferramentas da interface.
        session_id: Identificador da sessão, para a auditoria.
        core: Módulo do app com o banco, o índice e as constantes (`main`). O Chainlit
            passa o próprio módulo; sem ele, `main` é importado (caso da API do site).

    Returns:
        O `Outcome` da mensagem; recusas voltam com `blocked=True`.
    """
    import asyncio

    if core is None:
        import main as core

    engine = core.get_engine()
    limits = core.get_limits()
    stages: list[dict[str, Any]] = []
    trace_id = uuid.uuid4().hex[:12]

    async def stage(name: str, **details: Any) -> None:
        item = {"stage": name, **details}
        stages.append(item)
        notify = getattr(hooks, "on_stage", None)
        if notify:
            await notify(item)

    async def refuse(reply: str, reasons: tuple[str, ...], risk: int, event: str, label: str) -> Outcome:
        await asyncio.to_thread(
            log_conversation,
            engine,
            usuario_id=usuario.usuario_id,
            papel=usuario.papel,
            sessao_id=session_id,
            pergunta=text,
            bloqueada=True,
            motivos=reasons,
            risco=risk,
            trace_id=trace_id,
            rota="bloqueada",
        )
        await asyncio.to_thread(log_event, engine, event, usuario.usuario_id, ", ".join(reasons))
        return Outcome(
            answer=reply, route="bloqueada", route_reason=label, blocked=True,
            reasons=reasons, risk=risk, trace_id=trace_id, stages=stages,
        )

    # 1. Pausa por atividade suspeita e limite de mensagens.
    # As duas consultas são independentes: em paralelo, a espera é a de uma ida ao banco só.
    score, decision = await asyncio.gather(
        asyncio.to_thread(limits.risk_score, usuario.usuario_id),
        asyncio.to_thread(limits.message_decision, usuario.usuario_id),
    )
    await stage("limites", pausado=risk_paused(score), pontos_de_risco=score, permitido=decision.allowed)
    if risk_paused(score):
        return await refuse(core.MSG_PAUSED, ("usuario_pausado",), 0, "usuario_pausado", "usuário pausado")
    if not decision.allowed:
        return await refuse(
            core.MSG_RATE_LIMIT.format(seconds=decision.retry_after),
            ("limite_de_mensagens",), 0, "limite_excedido", "limite de mensagens",
        )

    # 2. Injeção de prompt e tamanho; na zona cinzenta, um modelo leve dá o segundo parecer.
    verdict = check_input(text)
    judged = False
    if verdict.suspicious and verdict.allowed:
        judged = True
        opinion = await judge_injection(verdict.sanitized)
        if opinion.attack:
            verdict = replace(
                verdict, allowed=False, risk=max(verdict.risk, BLOCK_THRESHOLD), reasons=(*verdict.reasons, "juiz_modelo")
            )
    await stage("guardrails", risco=verdict.risk, motivos=list(verdict.reasons), permitido=verdict.allowed, juiz_chamado=judged)
    if not verdict.allowed:
        return await refuse(core.MSG_BLOCKED, verdict.reasons, verdict.risk, "mensagem_bloqueada", "guardrail")

    # 3. Roteamento.
    history = state.agent_history
    sticky = bool(history) and history[-1]["role"] == "assistant" and history[-1]["content"].rstrip().endswith("?")
    chosen = route(verdict.sanitized, continuing_agent=sticky)
    await stage("roteador", rota=chosen.name, faixa=chosen.tier, regra=chosen.reason)

    sources: list[str] = []
    events: list[ToolEvent] = []
    cost = 0.0
    model = ""
    cache_hit = False
    cache_candidate: tuple[list[float], str, str] | None = None
    start = time.perf_counter()

    if chosen.name == "smalltalk":
        answer = smalltalk_reply(verdict.sanitized, usuario.nome.split()[0])
        model = "resposta pronta"
        reference = reference_cost(120, 80)
    elif chosen.name == "agent" and not ferramentas_permitidas(usuario.papel):
        answer = NO_TOOLS_MESSAGE
        model = "sem ferramentas"
        reference = 0.0
    elif chosen.name == "agent":
        await core.HUB.start()
        wrapped = _LoggingHooks(hooks, engine, usuario, trace_id, events)
        outcome = await run_agent(verdict.sanitized, usuario, core.HUB, wrapped, history=history[-8:])
        answer, cost, model, reference = outcome.answer, outcome.cost, outcome.model, outcome.reference_cost
        state.agent_history = [*history, {"role": "user", "content": verdict.sanitized}, {"role": "assistant", "content": answer}][-8:]
        await stage("agente", passos=outcome.steps, ferramentas=[e.qualified_name for e in events])
    else:
        scope = cache_scope(usuario.papel)
        version = (core.read_index_metadata() or {}).get("data_hash", "")[:16]
        vector = await embed_query(core, verdict.sanitized)
        hit = await asyncio.to_thread(cache_lookup, engine, vector, scope, version) if vector else None
        await stage("cache", acerto=bool(hit), escopo=scope, similaridade=round(hit.similarity, 3) if hit else None)

        if hit:
            answer = hit.answer
            model = "cache semântico"
            reference = reference_cost(900, 120)
            cache_hit = True
        elif vector is None:
            # Sem vetor não há busca: avisa em vez de responder sem consultar a base.
            answer = MSG_EMBEDDINGS_DOWN
            model = "indisponível"
        else:
            query_engine = await asyncio.to_thread(core.get_query_engine, usuario)
            response = await asyncio.to_thread(query_engine.query, verdict.sanitized)
            answer = str(response)
            nodes = getattr(response, "source_nodes", [])
            sources = [f"{n.metadata.get('tipo')}:{n.metadata.get(str(n.metadata.get('tipo')) + '_id')}" for n in nodes]
            prompt_tokens = (len(core.SYSTEM_PROMPT) + sum(len(n.get_content()) for n in nodes) + len(verdict.sanitized)) // 4
            cost = estimate_cost(get_tiers()["standard"], prompt_tokens, len(answer) // 4)
            reference = reference_cost(prompt_tokens, len(answer) // 4)
            model = get_tiers()["standard"].model
            await stage("rag", documentos=sources)
            if is_cacheable(verdict.sanitized, [n.metadata for n in nodes], answer, usuario.papel):
                cache_candidate = (vector, scope, version)

    if chosen.name != "agent":
        state.agent_history = []  # quem perguntou outra coisa não fica preso ao agente

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "Rota %s concluída em %.2fs (custo simulado US$ %.6f; referência US$ %.6f).",
        chosen.name, elapsed_ms / 1000, cost, reference,
    )

    # 4. Saída: nada de prompt de sistema vazado nem dados pessoais sensíveis.
    reasons = verdict.reasons
    risk = verdict.risk
    if leaks_system_prompt(answer, core.LEAK_CHECK_TEXT, window=10):
        answer = core.MSG_BLOCKED
        reasons = (*reasons, "vazamento_de_prompt")
        risk = max(risk, 60)
    answer = redact(answer, include_email=False)
    if cache_hit:
        reasons = (*reasons, "cache_hit")
    elif cache_candidate and "vazamento_de_prompt" not in reasons:
        await asyncio.to_thread(cache_store, engine, *cache_candidate, verdict.sanitized, answer)
    await stage("saida", vazamento="vazamento_de_prompt" in reasons)

    await asyncio.to_thread(
        log_conversation,
        engine,
        usuario_id=usuario.usuario_id,
        papel=usuario.papel,
        sessao_id=session_id,
        pergunta=text,
        resposta=answer,
        motivos=reasons,
        risco=risk,
        documentos=sources,
        latencia_ms=elapsed_ms,
        modelo=model,
        trace_id=trace_id,
        rota=chosen.name,
        custo_simulado=cost,
        custo_referencia=reference,
    )
    await stage("auditoria", trace_id=trace_id)

    return Outcome(
        answer=answer, route=chosen.name, route_reason=chosen.reason, model=model, cost=cost,
        reference_cost=reference, latency_ms=elapsed_ms, reasons=reasons, risk=risk, cache_hit=cache_hit,
        sources=sources, tool_events=events, trace_id=trace_id, stages=stages,
    )
