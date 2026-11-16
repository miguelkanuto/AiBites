import type { Answer } from "../api";

type NodeDef = { id: string; x: number; y: number; w: number; h: number; title: string; sub?: string };

const NODES: NodeDef[] = [
  { id: "mensagem", x: 10, y: 215, w: 110, h: 60, title: "Mensagem", sub: "usuário logado" },
  { id: "limites", x: 150, y: 215, w: 130, h: 60, title: "Limites e risco", sub: "por usuário (banco)" },
  { id: "guardrails", x: 310, y: 215, w: 140, h: 60, title: "Guardrails", sub: "regras + juiz leve" },
  { id: "roteador", x: 480, y: 215, w: 120, h: 60, title: "Roteador", sub: "3 faixas de modelo" },
  { id: "pronta", x: 650, y: 40, w: 150, h: 56, title: "Resposta pronta", sub: "sem modelo · custo 0" },
  { id: "cache", x: 650, y: 150, w: 150, h: 56, title: "Cache semântico", sub: "pgvector · por papel" },
  { id: "rag", x: 650, y: 235, w: 150, h: 56, title: "RAG com RBAC", sub: "híbrido · filtro no SQL" },
  { id: "agente", x: 650, y: 350, w: 150, h: 56, title: "Agente", sub: "modelo forte · política" },
  { id: "mcp", x: 840, y: 350, w: 150, h: 56, title: "Servidores MCP", sub: "RH · TI · Slack · Vendas" },
  { id: "saida", x: 840, y: 215, w: 150, h: 60, title: "Filtro de saída", sub: "prompt vazado · dados pessoais" },
  { id: "auditoria", x: 840, y: 100, w: 150, h: 56, title: "Auditoria", sub: "conversas · ferramentas" },
];

const EDGES: [string, string][] = [
  ["mensagem", "limites"],
  ["limites", "guardrails"],
  ["guardrails", "roteador"],
  ["roteador", "pronta"],
  ["roteador", "cache"],
  ["cache", "rag"],
  ["roteador", "agente"],
  ["agente", "mcp"],
  ["rag", "saida"],
  ["mcp", "saida"],
  ["pronta", "saida"],
  ["saida", "auditoria"],
];

/** Ligação entre dois blocos: vertical se estão na mesma coluna, curva lateral nos demais casos. */
function edgePath(a: NodeDef, b: NodeDef): string {
  if (a.x === b.x) {
    const down = b.y > a.y;
    const x = a.x + a.w / 2;
    return `M${x},${down ? a.y + a.h : a.y} L${x},${down ? b.y : b.y + b.h}`;
  }
  const x1 = a.x + a.w;
  const y1 = a.y + a.h / 2;
  const x2 = b.x;
  const y2 = b.y + b.h / 2;
  const mid = (x1 + x2) / 2;
  return `M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`;
}

function activeSet(answer: Answer | null): { on: Set<string>; bad: Set<string> } {
  const on = new Set<string>();
  const bad = new Set<string>();
  if (!answer) return { on, bad };

  on.add("mensagem");
  for (const stage of answer.etapas) {
    if (["limites", "guardrails", "roteador", "cache", "rag", "saida", "auditoria"].includes(stage.stage)) on.add(stage.stage);
    if (stage.stage === "agente") {
      on.add("agente");
      on.add("mcp");
    }
  }
  if (answer.rota === "smalltalk") on.add("pronta");
  if (answer.rota === "agent") {
    on.add("agente");
    if (answer.ferramentas.length > 0) on.add("mcp");
  }
  if (answer.rota === "rag") on.add("cache");
  if (answer.bloqueada) {
    bad.add("guardrails");
    on.add("auditoria");
  }
  return { on, bad };
}

function Diagram({ answer }: { answer: Answer | null }) {
  const byId = Object.fromEntries(NODES.map((node) => [node.id, node]));
  const { on, bad } = activeSet(answer);

  return (
    <svg className="diagram" viewBox="0 0 1010 430" role="img" aria-label="Caminho de uma mensagem pelo sistema">
      {EDGES.map(([from, to]) => {
        const lit = on.has(from) && on.has(to);
        return <path key={`${from}-${to}`} className={`edge ${lit ? "on" : ""}`} d={edgePath(byId[from], byId[to])} />;
      })}
      {NODES.map((node) => (
        <g key={node.id} className={`node ${bad.has(node.id) ? "bad" : on.has(node.id) ? "on" : ""}`}>
          <rect x={node.x} y={node.y} width={node.w} height={node.h} rx={12} />
          <text x={node.x + node.w / 2} y={node.y + node.h / 2 - 2} textAnchor="middle">{node.title}</text>
          {node.sub && <text className="sub" x={node.x + node.w / 2} y={node.y + node.h / 2 + 14} textAnchor="middle">{node.sub}</text>}
        </g>
      ))}
    </svg>
  );
}

const DECISIONS: { titulo: string; texto: string }[] = [
  {
    titulo: "Permissão no banco, não no prompt",
    texto:
      "Cada documento indexado tem nível e dono. O filtro de acesso vira condição SQL no pgvector, então o que o usuário não pode ver nunca chega ao modelo. Uma segunda checagem no código barra qualquer sobra. Um ataque de injeção não consegue vazar o que o modelo nunca recebeu.",
  },
  {
    titulo: "O modelo propõe, o app decide",
    texto:
      "No agente, o modelo só vê as ferramentas do papel do usuário. Cada chamada passa pela política no app e de novo no servidor MCP, ações que alteram algo pedem confirmação, e a identidade vai num contexto assinado (HMAC, 2 min) que o modelo nunca vê nem forja.",
  },
  {
    titulo: "Contas exatas em SQL, não no modelo",
    texto:
      "Somas e rankings vêm de ferramentas com consultas parametrizadas e só leitura. O RAG responde os \"qual\" e \"quais\"; o PostgreSQL faz a matemática. O resultado bate com a conta feita direto no banco (há teste para isso).",
  },
  {
    titulo: "Busca híbrida e documentos em frase",
    texto:
      "Medi variantes com 10 perguntas de teste: o acerto subiu de 0,38 para 0,98 ao escrever cada linha como frase, juntar busca vetorial com palavra-chave em português e buscar cadastros e vendas em separado. É uma amostra pequena, boa para comparar variantes, não uma garantia.",
  },
  {
    titulo: "Roteador e cache para controlar custo",
    texto:
      "Cumprimentos têm resposta pronta, consultas vão para a faixa padrão e só ações e contas exatas usam o modelo forte. O cache semântico só guarda respostas montadas com documentos que o papel enxerga pelo nível, com chave por papel, validade e versão dos dados.",
  },
  {
    titulo: "Menor privilégio e auditoria que não se edita",
    texto:
      "O app conecta com um usuário que lê o negócio e só insere nos logs: não edita nem apaga. O dono do banco só aparece para seed e recriação do índice. Limites de login, mensagens e risco saem das próprias tabelas de auditoria, então valem entre reinícios.",
  },
];

const FAKE: string[] = [
  "Os dados (produtos, vendedores, vendas, funcionários) são fictícios.",
  "RH, TI e Slack são sistemas simulados, cada um em um servidor MCP próprio; não há integração com Jira, Slack ou RH reais.",
  "O custo é simulado com preços de referência por faixa; os modelos de linguagem são reais e gratuitos (OpenRouter).",
  "O acesso do site é por personas fictícias, sem senha, e existe só para demonstração.",
];

const LIMITS: string[] = [
  "Guardrails por regras e um juiz de modelo pequeno reduzem o risco, mas não o eliminam. Quem protege os dados é o RBAC no banco e a política de ferramentas.",
  "O agente pode acrescentar detalhes que o resultado da ferramenta não trouxe. O prompt pede para não fazer isso, mas não é garantido.",
  "Os modelos gratuitos têm limite diário e de provedor; o agente usa mais chamadas que o RAG.",
  "Ainda falta a suíte de avaliação com bloqueio de release, o empacotamento em Docker e o login com Google.",
];

export function Architecture({ answer }: { answer: Answer | null }) {
  return (
    <div className="container page stack">
      <div className="page-head">
        <h1>Como foi feito</h1>
        <p>
          A Carol é uma assistente corporativa fictícia da AiBites. Este projeto mostra, de ponta a ponta, o que importa quando um assistente
          de IA vai trabalhar com dados de uma empresa grande: quem pode ver o quê, o que o modelo pode fazer sozinho, quanto custa e como
          auditar.
        </p>
      </div>

      <div className="card">
        <h3>O caminho de uma mensagem</h3>
        <p className="muted small">
          {answer
            ? "Os blocos acesos são os do último passo que você enviou na aba Demonstração."
            : "Envie uma mensagem na aba Demonstração e os blocos pelos quais ela passou se acendem aqui."}
        </p>
        <Diagram answer={answer} />
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        {DECISIONS.map((decision) => (
          <div className="card" key={decision.titulo}>
            <h3>{decision.titulo}</h3>
            <p className="muted" style={{ marginBottom: 0 }}>{decision.texto}</p>
          </div>
        ))}
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        <div className="card">
          <h3>Stack</h3>
          <div className="row">
            {["Python 3.13", "FastAPI", "React + TypeScript", "PostgreSQL + pgvector", "LlamaIndex", "MCP", "Chainlit", "OpenRouter", "HuggingFace (embeddings locais)", "pytest"].map((item) => (
              <span className="chip" key={item}>{item}</span>
            ))}
          </div>
          <p className="muted small" style={{ marginTop: 12 }}>
            O mesmo pipeline atende o chat do Chainlit e esta API; regras de segurança valem igual nas duas interfaces. Mais de 340 testes
            (política, senhas, guardrails, roteador, agente com modelo falso, cache, ferramentas MCP reais e busca por papel) rodam sem chamar
            o LLM.
          </p>
        </div>
        <div className="card">
          <h3>O que é simulado</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {FAKE.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      </div>

      <div className="card">
        <h3>Limites conhecidos e próximos passos</h3>
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
          {LIMITS.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </div>
    </div>
  );
}
