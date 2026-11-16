import type { Answer } from "../api";
import { percent, usd } from "../api";

const ROUTE_LABEL: Record<string, string> = {
  smalltalk: "resposta pronta",
  rag: "consulta à base (RAG)",
  agent: "agente com ferramentas",
  bloqueada: "bloqueada",
};

const STAGE_LABEL: Record<string, string> = {
  limites: "Limites e risco do usuário",
  guardrails: "Guardrails de entrada",
  roteador: "Roteador",
  cache: "Cache semântico",
  rag: "Busca na base (RBAC no banco)",
  agente: "Agente",
  saida: "Filtro de saída",
  auditoria: "Auditoria gravada",
};

function stageDetail(stage: Answer["etapas"][number]): string {
  switch (stage.stage) {
    case "limites":
      return `risco acumulado ${stage.pontos_de_risco}${stage.permitido ? "" : " · limite atingido"}`;
    case "guardrails":
      return `risco ${stage.risco}${stage.juiz_chamado ? " · juiz de modelo chamado" : ""}${(stage.motivos as string[]).length ? ` · ${(stage.motivos as string[]).join(", ")}` : ""}`;
    case "roteador":
      return `${ROUTE_LABEL[stage.rota as string] ?? stage.rota}`;
    case "cache":
      return stage.acerto ? `ACERTO (similaridade ${stage.similaridade})` : "sem acerto";
    case "rag":
      return `${(stage.documentos as string[]).length} documentos`;
    case "agente":
      return `${stage.passos} passos · ${(stage.ferramentas as string[]).join(", ") || "sem ferramentas"}`;
    default:
      return "";
  }
}

export function Inspector({ answer }: { answer: Answer | null }) {
  if (!answer) {
    return (
      <div className="card inspector">
        <h3>Inspetor</h3>
        <p className="muted small">
          Envie uma mensagem e veja aqui o que aconteceu por dentro: rota escolhida, modelo, custo simulado, cache, guardrails, documentos e
          ferramentas.
        </p>
      </div>
    );
  }

  const ref = answer.custo_referencia || 0;
  const share = ref > 0 ? Math.min(1, answer.custo_simulado / ref) : 0;

  return (
    <div className="card inspector stack">
      <div>
        <h3>Inspetor</h3>
        <div className="row">
          <span className={`chip ${answer.bloqueada ? "bad" : "accent"}`}>{ROUTE_LABEL[answer.rota] ?? answer.rota}</span>
          {answer.cache && <span className="chip ok">cache semântico</span>}
          {answer.risco >= 30 && <span className={`chip ${answer.risco >= 60 ? "bad" : "warn"}`}>risco {answer.risco}</span>}
        </div>
      </div>

      <dl className="kv">
        <dt>Modelo</dt>
        <dd className="mono">{answer.modelo || "—"}</dd>
        <dt>Latência</dt>
        <dd>{answer.latencia_ms} ms</dd>
        <dt>Regra do roteador</dt>
        <dd className="mono">{answer.motivo_da_rota}</dd>
        <dt>Trace</dt>
        <dd className="mono">{answer.trace_id}</dd>
      </dl>

      <div>
        <h4>Custo simulado</h4>
        <div className="small">Esta resposta: {usd(answer.custo_simulado)}</div>
        <div className="bar">
          <span style={{ width: `${Math.max(2, share * 100)}%` }} />
        </div>
        <div className="small muted" style={{ marginTop: 6 }}>
          Se fosse sempre o modelo forte: {usd(answer.custo_referencia)}
        </div>
        <div className="bar ref">
          <span style={{ width: "100%" }} />
        </div>
        {ref > 0 && <div className="small ok yes" style={{ marginTop: 6 }}>Economia do roteamento: {percent(answer.economia)}</div>}
      </div>

      <div>
        <h4>Caminho da mensagem</h4>
        <div className="timeline">
          {answer.etapas.map((stage, index) => (
            <div className="step" key={index}>
              <span className="num">{index + 1}</span>
              <span>
                <strong>{STAGE_LABEL[stage.stage] ?? stage.stage}</strong>
                <span className="muted"> {stageDetail(stage)}</span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {answer.fontes.length > 0 && (
        <div>
          <h4>Documentos usados</h4>
          <div className="row">
            {answer.fontes.map((source) => (
              <span className="chip" key={source}>
                {source}
              </span>
            ))}
          </div>
        </div>
      )}

      {answer.ferramentas.length > 0 && (
        <div>
          <h4>Ferramentas</h4>
          {answer.ferramentas.map((tool, index) => (
            <div key={index} className="small" style={{ marginBottom: 6 }}>
              <span className={`chip ${tool.status === "ok" ? "ok" : tool.status === "cancelado" ? "warn" : "bad"}`}>{tool.status}</span>{" "}
              <span className="mono">{tool.nome}</span> <span className="muted">{tool.duracao_ms} ms</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
