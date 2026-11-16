import { useCallback, useEffect, useState } from "react";
import type { Answer, Health, Persona } from "./api";
import { ApiError, api, post } from "./api";
import { Architecture } from "./components/Architecture";
import { Avatar } from "./components/Avatars";
import { Logo } from "./components/Brand";
import { Chat } from "./components/Chat";
import { Footer, Home } from "./components/Home";
import type { Tab } from "./components/Home";
import { Inspector } from "./components/Inspector";
import { Lab } from "./components/Lab";
import { Metrics } from "./components/Metrics";

const TABS: { id: Tab; label: string }[] = [
  { id: "inicio", label: "Início" },
  { id: "demo", label: "Demonstração" },
  { id: "lab", label: "Laboratório" },
  { id: "arquitetura", label: "Como foi feito" },
  { id: "metricas", label: "Métricas" },
];

function Demo({ ready, initialPersona, onAnswer }: { ready: boolean; initialPersona?: string; onAnswer: (answer: Answer) => void }) {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [active, setActive] = useState<Persona | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");

  const choose = useCallback(async (persona: Persona) => {
    setError("");
    try {
      await post("/api/session", { persona_id: persona.id });
      setActive(persona);
      setAnswer(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível iniciar a sessão.");
    }
  }, []);

  useEffect(() => {
    api<Persona[]>("/api/personas")
      .then(async (list) => {
        setPersonas(list);
        const wanted = list.find((p) => p.id === initialPersona);
        if (wanted) {
          await choose(wanted);
          return;
        }
        // Retoma a sessão existente, se houver.
        try {
          const current = await api<{ persona: Persona }>("/api/session");
          setActive(list.find((p) => p.id === current.persona.id) ?? null);
        } catch {
          /* sem sessão ainda */
        }
      })
      .catch(() => setError("A API não respondeu. Ela está rodando?"));
  }, [initialPersona, choose]);

  return (
    <div className="container page">
      <div className="page-head">
        <h1>Converse com a Carol</h1>
        <p>
          Escolha quem você quer ser e faça a mesma pergunta com perfis diferentes. Tudo aqui é fictício: dados, RH, TI e Slack são simulados, e o
          custo exibido também.
        </p>
      </div>
      {error && <div className="notice notice-bad">{error}</div>}

      <div className="demo-grid">
        <div className="persona-list" role="list" aria-label="Personas">
          {personas.map((persona) => (
            <button
              key={persona.id}
              role="listitem"
              className={`persona-item ${active?.id === persona.id ? "active" : ""}`}
              aria-pressed={active?.id === persona.id}
              onClick={() => choose(persona)}
            >
              <span className="avatar sm">
                <Avatar persona={persona.id} />
              </span>
              <span className="persona-item-text">
                <strong>{persona.nome}</strong>
                <span>{persona.titulo}</span>
                <small>{persona.descricao}</small>
              </span>
            </button>
          ))}
        </div>

        {active ? (
          <Chat
            persona={active}
            ready={ready}
            onAnswer={(a) => {
              setAnswer(a);
              onAnswer(a);
            }}
          />
        ) : (
          <div className="card empty-state">
            <h3>Escolha uma persona para começar</h3>
            <p>Cada uma enxerga dados e usa ferramentas diferentes.</p>
          </div>
        )}

        <Inspector answer={answer} />
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("inicio");
  const [personaId, setPersonaId] = useState<string | undefined>();
  const [health, setHealth] = useState<Health | null>(null);
  const [lastAnswer, setLastAnswer] = useState<Answer | null>(null);

  const go = useCallback((next: Tab, persona?: string) => {
    setPersonaId(persona);
    setTab(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const h = await api<Health>("/api/health");
        if (alive) setHealth(h);
        if (alive && !h.pronto && !h.error) setTimeout(poll, 3000);
      } catch {
        if (alive) {
          setHealth(null);
          setTimeout(poll, 5000);
        }
      }
    };
    void poll();
    return () => {
      alive = false;
    };
  }, []);

  const status =
    health === null
      ? { text: "API fora do ar", cls: "bad" }
      : health.error
        ? { text: "com erro", cls: "bad" }
        : health.pronto
          ? { text: "Carol pronta", cls: "ok" }
          : { text: "Carol acordando…", cls: "wait" };

  return (
    <div className="app">
      <header className="topbar">
        <div className="container topbar-inner">
          <button className="brand" onClick={() => go("inicio")} aria-label="AiBites, ir para o início">
            <Logo size={30} />
          </button>
          <nav className="tabs" aria-label="Seções">
            {TABS.map((item) => (
              <button key={item.id} className={`tab ${tab === item.id ? "active" : ""}`} aria-current={tab === item.id ? "page" : undefined} onClick={() => go(item.id)}>
                {item.label}
              </button>
            ))}
          </nav>
          <div className="status" title={health?.error || ""} role="status">
            <span className={`dot ${status.cls}`} />
            {status.text}
          </div>
        </div>
      </header>

      {tab === "inicio" && <Home go={go} />}
      {tab === "demo" && <Demo ready={Boolean(health?.pronto)} initialPersona={personaId} onAnswer={setLastAnswer} />}
      {tab === "lab" && <Lab />}
      {tab === "arquitetura" && <Architecture answer={lastAnswer} />}
      {tab === "metricas" && <Metrics />}

      <Footer />
    </div>
  );
}
