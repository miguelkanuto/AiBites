export type Prompt = { texto: string; demonstra: string };

export type Persona = {
  id: string;
  nome: string;
  titulo: string;
  papel: string;
  descricao: string;
  niveis: string[];
  ferramentas: string[];
  canais: string[];
  prompts: Prompt[];
};

export type ToolEvent = {
  nome: string;
  servidor: string;
  ferramenta: string;
  argumentos: Record<string, unknown>;
  status: "ok" | "erro" | "negado" | "cancelado";
  resultado: string;
  duracao_ms: number;
  confirmada: boolean | null;
};

export type Stage = { stage: string; [key: string]: unknown };

export type Answer = {
  resposta: string;
  rota: string;
  motivo_da_rota: string;
  modelo: string;
  custo_simulado: number;
  custo_referencia: number;
  economia: number;
  latencia_ms: number;
  bloqueada: boolean;
  motivos: string[];
  risco: number;
  cache: boolean;
  fontes: string[];
  ferramentas: ToolEvent[];
  trace_id: string;
  etapas: Stage[];
};

export type Confirm = { id: string; resumo: string; expira_em: number };

export type Health = { ok: boolean; pronto: boolean; index: boolean; tools: boolean; error: string; demo: boolean };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* corpo vazio */
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const post = <T,>(url: string, body: unknown) => api<T>(url, { method: "POST", body: JSON.stringify(body) });

type Handlers = {
  onStage: (stage: Stage) => void;
  onTool: (tool: ToolEvent) => void;
  onConfirm: (confirm: Confirm) => void;
  onAnswer: (answer: Answer) => void;
  onError: (message: string) => void;
};

/** Envia a mensagem e lê o fluxo SSE (`stage`, `tool`, `confirm`, `answer`, `error`). */
export async function streamChat(message: string, handlers: Handlers): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!response.ok || !response.body) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* sem corpo */
    }
    handlers.onError(detail);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (block: string) => {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trim());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    if (event === "stage") handlers.onStage(payload);
    else if (event === "tool") handlers.onTool(payload);
    else if (event === "confirm") handlers.onConfirm(payload);
    else if (event === "answer") handlers.onAnswer(payload);
    else if (event === "error") handlers.onError(payload.mensagem ?? "Erro inesperado.");
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let index: number;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      if (block.trim()) dispatch(block);
    }
  }
}

export const usd = (value: number) => (value === 0 ? "US$ 0" : `US$ ${value.toFixed(value < 0.01 ? 5 : 4)}`);
export const percent = (value: number) => `${Math.round(value * 100)}%`;
