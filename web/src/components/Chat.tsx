import { useEffect, useRef, useState } from "react";
import type { Answer, Confirm, Persona, Stage, ToolEvent } from "../api";
import { post, streamChat } from "../api";

type Message =
  | { kind: "user"; text: string }
  | { kind: "bot"; text: string; answer: Answer }
  | { kind: "error"; text: string }
  | { kind: "tool"; tool: ToolEvent };

const STAGE_TEXT: Record<string, string> = {
  limites: "conferindo limites…",
  guardrails: "analisando a mensagem…",
  roteador: "escolhendo o caminho…",
  cache: "olhando o cache…",
  rag: "lendo a base…",
  agente: "usando ferramentas…",
  saida: "revisando a resposta…",
  auditoria: "registrando…",
};

type Props = {
  persona: Persona;
  ready: boolean;
  onAnswer: (answer: Answer) => void;
};

export function Chat({ persona, ready, onAnswer }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([]);
    setConfirm(null);
  }, [persona.id]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, stage, confirm]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setStage("enviando…");
    setMessages((current) => [...current, { kind: "user", text: message }]);

    await streamChat(message, {
      onStage: (s: Stage) => setStage(STAGE_TEXT[s.stage] ?? s.stage),
      onTool: (tool) => setMessages((current) => [...current, { kind: "tool", tool }]),
      onConfirm: (c) => setConfirm(c),
      onAnswer: (answer) => {
        setMessages((current) => [...current, { kind: "bot", text: answer.resposta, answer }]);
        onAnswer(answer);
      },
      onError: (error) => setMessages((current) => [...current, { kind: "error", text: error }]),
    }).catch(() => setMessages((current) => [...current, { kind: "error", text: "Não consegui falar com a API." }]));

    setBusy(false);
    setStage("");
    setConfirm(null);
  }

  async function decide(ok: boolean) {
    if (!confirm) return;
    const id = confirm.id;
    setConfirm(null);
    await post("/api/confirm", { id, ok }).catch(() => undefined);
  }

  return (
    <div className="card chatbox">
      <div className="messages">
        {messages.length === 0 && (
          <div className="muted small">
            Você está como <strong>{persona.nome}</strong> ({persona.titulo}). Escolha uma pergunta sugerida abaixo ou escreva a sua.
          </div>
        )}

        {messages.map((message, index) => {
          if (message.kind === "user") return <div key={index} className="msg user">{message.text}</div>;
          if (message.kind === "error") return <div key={index} className="msg bot blocked">{message.text}</div>;
          if (message.kind === "tool") {
            const t = message.tool;
            return (
              <div key={index} className="tool">
                <span className={`chip ${t.status === "ok" ? "ok" : t.status === "cancelado" ? "warn" : "bad"}`}>{t.status}</span>{" "}
                <span className="mono">{t.nome}</span>
                <div className="muted mono" style={{ marginTop: 4 }}>{JSON.stringify(t.argumentos)}</div>
              </div>
            );
          }
          return (
            <div key={index} className={`msg bot ${message.answer.bloqueada ? "blocked" : ""}`}>
              {message.text}
              <div className="meta">
                <span className="chip accent">{message.answer.rota}</span>
                {message.answer.cache && <span className="chip ok">cache</span>}
                <span className="chip">{message.answer.latencia_ms} ms</span>
              </div>
            </div>
          );
        })}

        {confirm && (
          <div className="confirm">
            <strong>Posso fazer isto?</strong>
            <p style={{ margin: "6px 0 10px" }}>{confirm.resumo}</p>
            <div className="row">
              <button className="btn" onClick={() => decide(true)}>Confirmar</button>
              <button className="btn danger" onClick={() => decide(false)}>Cancelar</button>
            </div>
          </div>
        )}

        {busy && !confirm && <div className="typing">Carol: {stage}</div>}
        <div ref={end} />
      </div>

      <div className="suggestions">
        {persona.prompts.map((prompt) => (
          <button key={prompt.texto} className="suggestion" disabled={busy || !ready} onClick={() => send(prompt.texto)}>
            {prompt.texto}
            <span className="why">{prompt.demonstra}</span>
          </button>
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send(input);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={ready ? "Pergunte algo à Carol…" : "Carregando o assistente (cerca de 40 s)…"}
          disabled={busy || !ready}
          maxLength={1000}
        />
        <button className="btn" disabled={busy || !ready || !input.trim()}>Enviar</button>
      </form>
    </div>
  );
}
