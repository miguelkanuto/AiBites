"""API do site de demonstração (FastAPI).

Usa o mesmo pipeline do chat do Chainlit (`pipeline.process_message`), então
RBAC, guardrails, roteador, cache, agente e auditoria valem igual. Também expõe
simuladores sem custo (guardrails, roteador, RBAC, cache) para o laboratório do site.

Rodar (na raiz do projeto):
    uv run uvicorn web_api:app --app-dir src --port 8001

Sem senha: quem visita escolhe uma persona fictícia, desde que `AIBITES_SITE_DEMO=1`
(padrão ligado). Cada visitante ganha um id próprio, então limites e auditoria são por visitante.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

import cache as semantic_cache
from agent import ToolEvent
from guardrails import check_input, redact
from llm import ProviderUnavailable, estimate_cost, get_tiers, reference_cost
from personas import BY_ID, PERSONAS, Persona
from pipeline import ConversationState, Outcome, process_message
from rbac import NIVEIS, NIVEIS_POR_PAPEL, Usuario, pode_ver
from router import route
from version import VERSION, build_id
from tool_policy import FERRAMENTAS, canais_permitidos, exige_confirmacao, ferramentas_permitidas, pode_usar

logger = logging.getLogger("web_api")

COOKIE_NAME = "aibites_site"
SESSION_TTL_SECONDS = 2 * 3600
CONFIRM_TIMEOUT_SECONDS = 120
MAX_SESSIONS = 500
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

READY = {"index": False, "tools": False, "error": ""}


def demo_enabled() -> bool:
    """O login sem senha só existe com `AIBITES_SITE_DEMO=1` (padrão)."""
    return os.getenv("AIBITES_SITE_DEMO", "1") == "1"


# --- Sessões (em memória, por visitante) ---------------------------------


@dataclass
class SiteSession:
    sid: str
    persona: Persona
    usuario: Usuario
    state: ConversationState = field(default_factory=ConversationState)
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    busy: asyncio.Lock = field(default_factory=asyncio.Lock)
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)


SESSIONS: dict[str, SiteSession] = {}


def _secret() -> bytes:
    base = os.getenv("SITE_SESSION_SECRET") or os.getenv("CHAINLIT_AUTH_SECRET")
    if not base:
        raise RuntimeError("Defina SITE_SESSION_SECRET ou CHAINLIT_AUTH_SECRET.")
    return hmac.new(base.encode(), b"aibites-site-session", hashlib.sha256).digest()


def _sign(sid: str) -> str:
    return f"{sid}.{hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()[:32]}"


def _unsign(value: str) -> str | None:
    sid, _, signature = value.partition(".")
    expected = hmac.new(_secret(), sid.encode(), hashlib.sha256).hexdigest()[:32]
    return sid if sid and hmac.compare_digest(signature, expected) else None


def _cleanup() -> None:
    now = time.time()
    for sid in [k for k, v in SESSIONS.items() if now - v.touched > SESSION_TTL_SECONDS]:
        SESSIONS.pop(sid, None)
    if len(SESSIONS) > MAX_SESSIONS:
        for sid, _ in sorted(SESSIONS.items(), key=lambda item: item[1].touched)[: len(SESSIONS) - MAX_SESSIONS]:
            SESSIONS.pop(sid, None)


def current_session(request: Request) -> SiteSession:
    sid = _unsign(request.cookies.get(COOKIE_NAME, ""))
    session = SESSIONS.get(sid or "")
    if session is None or time.time() - session.touched > SESSION_TTL_SECONDS:
        raise HTTPException(status_code=401, detail="Sessão inexistente ou expirada. Escolha uma persona.")
    session.touched = time.time()
    return session


# --- Inicialização --------------------------------------------------------


def _warm() -> None:
    import main as core

    try:
        core.configure_llama_index()
        core.build_or_load_index()
        READY["index"] = True
    except Exception as error:
        logger.exception("Falha ao carregar o índice.")
        READY["error"] = str(error)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import main as core

    threading.Thread(target=_warm, daemon=True).start()

    async def start_tools() -> None:
        try:
            await core.HUB.start()
            READY["tools"] = not core.HUB.failures
            if core.HUB.failures:
                READY["error"] = f"servidores MCP com falha: {core.HUB.failures}"
        except Exception as error:
            logger.exception("Falha ao iniciar os servidores MCP.")
            READY["error"] = str(error)

    task = asyncio.create_task(start_tools())
    yield
    task.cancel()
    await core.HUB.stop()


app = FastAPI(title="AiBites · API do site", lifespan=lifespan)


# --- Modelos de requisição ------------------------------------------------


class SessionRequest(BaseModel):
    persona_id: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ConfirmRequest(BaseModel):
    id: str
    ok: bool


class TextRequest(BaseModel):
    text: str = Field(max_length=4000)


class RouteRequest(BaseModel):
    text: str = Field(max_length=4000)
    continuing_agent: bool = False


class RbacCheckRequest(BaseModel):
    papel: str
    nivel: str
    dono: str | None = None
    funcionario_id: str | None = None


class CacheCheckRequest(BaseModel):
    papel: str
    question: str = Field(max_length=1000)
    sources: list[dict[str, str]] = Field(default_factory=list)


# --- Utilidades de saída --------------------------------------------------


def persona_json(persona: Persona) -> dict[str, Any]:
    papel = persona.usuario.papel
    return {
        "id": persona.id,
        "nome": persona.usuario.nome,
        "titulo": persona.titulo,
        "papel": papel,
        "descricao": persona.descricao,
        "niveis": list(NIVEIS_POR_PAPEL.get(papel, ())),
        "ferramentas": ferramentas_permitidas(papel),
        "canais": canais_permitidos(papel),
        "prompts": [{"texto": p.texto, "demonstra": p.demonstra} for p in persona.prompts],
    }


def tool_event_json(event: ToolEvent) -> dict[str, Any]:
    return {
        "nome": event.qualified_name,
        "servidor": event.server,
        "ferramenta": event.tool,
        "argumentos": event.arguments,
        "status": event.status,
        "resultado": redact(event.result)[:1200],
        "duracao_ms": event.duration_ms,
        "confirmada": event.confirmed,
    }


def outcome_json(outcome: Outcome) -> dict[str, Any]:
    economia = 0.0
    if outcome.reference_cost > 0:
        economia = max(0.0, 1 - outcome.cost / outcome.reference_cost)
    return {
        "resposta": outcome.answer,
        "rota": outcome.route,
        "motivo_da_rota": outcome.route_reason,
        "modelo": outcome.model,
        "custo_simulado": round(outcome.cost, 6),
        "custo_referencia": round(outcome.reference_cost, 6),
        "economia": round(economia, 4),
        "latencia_ms": outcome.latency_ms,
        "bloqueada": outcome.blocked,
        "motivos": list(outcome.reasons),
        "risco": outcome.risk,
        "cache": outcome.cache_hit,
        "fontes": outcome.sources,
        "ferramentas": [tool_event_json(e) for e in outcome.tool_events],
        "trace_id": outcome.trace_id,
        "etapas": outcome.stages,
    }


class SiteHooks:
    """Liga o pipeline ao fluxo SSE: etapas, ferramentas e confirmações."""

    def __init__(self, session: SiteSession, queue: asyncio.Queue) -> None:
        self._session = session
        self._queue = queue

    async def on_stage(self, item: dict[str, Any]) -> None:
        await self._queue.put(("stage", item))

    async def on_tool(self, event: ToolEvent) -> None:
        await self._queue.put(("tool", tool_event_json(event)))

    async def confirm(self, summary: str) -> bool:
        confirm_id = uuid.uuid4().hex[:10]
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._session.pending[confirm_id] = future
        await self._queue.put(("confirm", {"id": confirm_id, "resumo": summary, "expira_em": CONFIRM_TIMEOUT_SECONDS}))
        try:
            return bool(await asyncio.wait_for(future, timeout=CONFIRM_TIMEOUT_SECONDS))
        except TimeoutError:
            return False
        finally:
            self._session.pending.pop(confirm_id, None)


# --- Saúde e sessão -------------------------------------------------------


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Estado da inicialização (o primeiro carregamento leva ~40 s)."""
    return {
        "ok": True, "pronto": READY["index"] and READY["tools"], **READY, "demo": demo_enabled(),
        "sessoes": len(SESSIONS), "versao": VERSION, "build": build_id(),
    }


@app.get("/api/personas")
async def personas() -> list[dict[str, Any]]:
    return [persona_json(p) for p in PERSONAS]


@app.post("/api/session")
async def create_session(body: SessionRequest, response: Response) -> dict[str, Any]:
    if not demo_enabled():
        raise HTTPException(status_code=403, detail="O login de demonstração está desligado.")
    persona = BY_ID.get(body.persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona desconhecida.")

    _cleanup()
    sid = secrets.token_hex(8)
    # Id próprio por visitante: limites e auditoria não se misturam entre quem visita.
    usuario = replace(persona.usuario, usuario_id=f"{persona.usuario.usuario_id}~{sid[:6]}")
    SESSIONS[sid] = SiteSession(sid, persona, usuario)
    response.set_cookie(
        COOKIE_NAME, _sign(sid), max_age=SESSION_TTL_SECONDS, httponly=True, samesite="lax",
        secure=os.getenv("AIBITES_SITE_SECURE_COOKIE") == "1",
    )
    return {"sessao": sid, "persona": persona_json(persona)}


@app.get("/api/session")
async def get_session(request: Request) -> dict[str, Any]:
    session = current_session(request)
    return {"sessao": session.sid, "persona": persona_json(session.persona)}


@app.delete("/api/session")
async def end_session(request: Request, response: Response) -> dict[str, bool]:
    sid = _unsign(request.cookies.get(COOKIE_NAME, ""))
    SESSIONS.pop(sid or "", None)
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


# --- Chat -----------------------------------------------------------------


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> EventSourceResponse:
    """Processa uma mensagem e devolve eventos SSE: `stage`, `tool`, `confirm`, `answer`, `error`."""
    session = current_session(request)
    if session.busy.locked():
        raise HTTPException(status_code=429, detail="Já existe uma mensagem em andamento nesta sessão.")
    if not READY["index"]:
        raise HTTPException(status_code=503, detail="O assistente ainda está carregando. Tente em alguns segundos.")

    queue: asyncio.Queue = asyncio.Queue()
    hooks = SiteHooks(session, queue)

    async def run() -> None:
        async with session.busy:
            try:
                outcome = await process_message(body.message, session.usuario, session.state, hooks, session_id=session.sid)
                await queue.put(("answer", outcome_json(outcome)))
            except Exception as error:
                logger.exception("Erro ao processar a mensagem.")
                mensagem = (
                    "Os modelos gratuitos estão sobrecarregados agora. Tente de novo em instantes."
                    if isinstance(error, ProviderUnavailable)
                    else "Algo deu errado ao processar a mensagem."
                )
                await queue.put(("error", {"mensagem": mensagem, "tipo": type(error).__name__}))
            finally:
                await queue.put(None)

    task = asyncio.create_task(run())

    async def events():
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                name, data = item
                yield {"event": name, "data": json.dumps(data, ensure_ascii=False, default=str)}
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(events())


@app.post("/api/confirm")
async def confirm(body: ConfirmRequest, request: Request) -> dict[str, bool]:
    session = current_session(request)
    future = session.pending.get(body.id)
    if future is None or future.done():
        raise HTTPException(status_code=404, detail="Confirmação inexistente ou expirada.")
    future.set_result(body.ok)
    return {"ok": True}


# --- Simuladores (sem LLM, sem escrita) -----------------------------------


@app.post("/api/sim/guardrails")
async def sim_guardrails(body: TextRequest) -> dict[str, Any]:
    """Mostra o que os guardrails de entrada decidiriam (o juiz de modelo não é chamado aqui)."""
    verdict = check_input(body.text)
    return {
        "permitido": verdict.allowed,
        "risco": verdict.risk,
        "suspeita": verdict.suspicious,
        "motivos": list(verdict.reasons),
        "texto_enviado_ao_modelo": verdict.sanitized,
        "limiar_de_bloqueio": 60,
        "limiar_de_suspeita": 30,
        "observacao": "Entre 30 e 59 o app chama um modelo leve para um segundo parecer; aqui ele não é chamado.",
    }


@app.post("/api/sim/route")
async def sim_route(body: RouteRequest) -> dict[str, Any]:
    """Rota escolhida e custo simulado em cada faixa (tokens estimados, sem chamar modelo)."""
    chosen = route(body.text, continuing_agent=body.continuing_agent)
    tokens_in, tokens_out = {"smalltalk": (120, 80), "rag": (900, 150), "agent": (4500, 250)}[chosen.name]
    tiers = get_tiers()
    return {
        "rota": chosen.name,
        "faixa": chosen.tier,
        "regra": chosen.reason,
        "tokens_estimados": {"entrada": tokens_in, "saida": tokens_out},
        "custo_por_faixa": {name: round(estimate_cost(tier, tokens_in, tokens_out), 6) for name, tier in tiers.items()},
        "custo_da_rota": 0.0 if chosen.name == "smalltalk" else round(estimate_cost(tiers[{"rag": "standard", "agent": "strong"}[chosen.name]], tokens_in, tokens_out), 6),
        "custo_se_tudo_fosse_forte": round(reference_cost(tokens_in, tokens_out), 6),
        "modelos": {name: tier.model for name, tier in tiers.items()},
    }


@app.get("/api/sim/rbac")
async def sim_rbac() -> dict[str, Any]:
    papeis = list(NIVEIS_POR_PAPEL)
    return {
        "niveis": list(NIVEIS),
        "papeis": papeis,
        "niveis_por_papel": {p: list(NIVEIS_POR_PAPEL[p]) for p in papeis},
        "ferramentas": {
            nome: {"papeis": sorted(pol.papeis), "escreve": pol.escreve, "confirmacao": exige_confirmacao(nome)}
            for nome, pol in FERRAMENTAS.items()
        },
        "canais": {p: canais_permitidos(p) for p in papeis},
    }


@app.post("/api/sim/rbac/check")
async def sim_rbac_check(body: RbacCheckRequest) -> dict[str, Any]:
    """Decide se um papel veria um documento (mesma função usada no app)."""
    usuario = Usuario("SIM", "Simulado", body.papel, funcionario_id=body.funcionario_id)
    metadata = {"nivel": body.nivel, **({"dono": body.dono} if body.dono else {})}
    pelo_nivel = body.nivel in NIVEIS_POR_PAPEL.get(body.papel, ())
    pode = pode_ver(usuario, metadata)
    motivo = "o nível está entre os do papel" if pelo_nivel else (
        "é um documento do próprio usuário" if pode else "nível fora do papel e documento de outra pessoa"
    )
    return {"pode_ver": pode, "motivo": motivo, "pelo_nivel": pelo_nivel}


@app.get("/api/sim/cache")
async def sim_cache() -> dict[str, Any]:
    return {
        "limiar_de_similaridade": semantic_cache.SIMILARITY_THRESHOLD,
        "validade_horas": semantic_cache.TTL_HOURS,
        "escopo_por_papel": {p: semantic_cache.scope_key(p) for p in NIVEIS_POR_PAPEL},
        "regras": [
            "Só guarda respostas montadas com documentos que o papel enxerga pelo nível.",
            "A chave inclui os níveis do papel: a resposta de um papel nunca vai para quem enxerga menos.",
            "Perguntas na primeira pessoa (meu, minha, eu) nunca entram.",
            "Cada entrada guarda a versão dos dados e expira; mudou o banco, o cache antigo deixa de valer.",
        ],
    }


@app.post("/api/sim/cache/check")
async def sim_cache_check(body: CacheCheckRequest) -> dict[str, Any]:
    ok = semantic_cache.is_cacheable(body.question, body.sources, "resposta", body.papel)
    return {"pode_ir_para_o_cache": ok, "escopo": semantic_cache.scope_key(body.papel)}


@app.get("/api/metrics")
async def metrics() -> dict[str, Any]:
    """Números agregados da auditoria (sem dados pessoais): rotas, cache, custo simulado e bloqueios."""
    import main as core

    try:
        with core.get_engine().connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT COALESCE(rota, 'sem_rota') AS rota, count(*) AS n, "
                    "COALESCE(round(avg(latencia_ms)), 0) AS latencia, "
                    "COALESCE(sum(custo_simulado) FILTER (WHERE custo_referencia IS NOT NULL), 0) AS custo, "
                    "COALESCE(sum(custo_referencia), 0) AS referencia, "
                    "count(*) FILTER (WHERE 'cache_hit' = ANY(motivos)) AS cache "
                    "FROM log_conversas WHERE criado_em > now() - interval '7 days' GROUP BY 1 ORDER BY 2 DESC"
                )
            ).all()
            tools = connection.execute(
                text(
                    "SELECT status, count(*) FROM tool_calls WHERE criado_em > now() - interval '7 days' GROUP BY 1 ORDER BY 2 DESC"
                )
            ).all()
            security = connection.execute(
                text(
                    "SELECT tipo, count(*) FROM eventos_seguranca WHERE criado_em > now() - interval '7 days' "
                    "AND tipo IN ('mensagem_bloqueada', 'limite_excedido', 'usuario_pausado', 'login_bloqueado') "
                    "GROUP BY 1 ORDER BY 2 DESC"
                )
            ).all()
    except Exception:
        logger.exception("Falha ao ler as métricas.")
        raise HTTPException(status_code=503, detail="Métricas indisponíveis.")

    total = sum(r.n for r in rows)
    cost = float(sum(r.custo for r in rows))
    reference = float(sum(r.referencia for r in rows))
    return {
        "janela_dias": 7,
        "mensagens": total,
        "custo_simulado": round(cost, 6),
        "custo_se_tudo_fosse_forte": round(reference, 6),
        "economia": round(max(0.0, 1 - cost / reference), 4) if reference > 0 else 0.0,
        "por_rota": [
            {"rota": r.rota, "mensagens": r.n, "latencia_media_ms": int(r.latencia), "custo": float(r.custo),
             "custo_referencia": float(r.referencia), "acertos_de_cache": r.cache}
            for r in rows
        ],
        "ferramentas": [{"status": s, "chamadas": n} for s, n in tools],
        "seguranca": [{"evento": t, "ocorrencias": n} for t, n in security],
    }


# --- Site estático (build do React), por último para não esconder a API ---

@app.middleware("http")
async def sem_cache_no_que_muda(request: Request, call_next):
    """A página (index.html) e a API nunca ficam em cache: quem abre o site recebe sempre a versão atual.
    Os arquivos em /assets têm hash no nome e podem ficar em cache.
    """
    response = await call_next(request)
    if not request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="site")
