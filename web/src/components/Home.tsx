import { useEffect, useState } from "react";
import type { Persona } from "../api";
import { api } from "../api";
import { useReveal, useTypewriter } from "../hooks";
import { Avatar } from "./Avatars";
import { Logo } from "./Brand";
import { Icon } from "./Icons";
import { ShieldSpot } from "./Spots";

export type Tab = "inicio" | "demo" | "lab" | "arquitetura" | "metricas";

type Props = { go: (tab: Tab, personaId?: string) => void };

const QUESTION = "Qual o valor do notebook Dell?";
const ANSWER = "O Notebook Dell Inspiron custa R$ 4.299,90 (preço unitário).";

function Reveal({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className={`reveal ${className}`}>
      {children}
    </div>
  );
}

function Hero({ go }: Props) {
  const [question, answer] = useTypewriter([QUESTION, ANSWER]);
  const done = answer.length === ANSWER.length;

  return (
    <section className="hero-store">
      <div className="container hero-grid">
        <div className="hero-copy">
          <h1>A Carol atende a AiBites: responde, resolve e só mostra o que você pode ver</h1>
          <p className="lead">
            Assistente de uma loja de eletrônicos que consulta produtos e vendas, abre ticket de TI, pede férias e calcula totais, cada pessoa
            com o seu acesso.
          </p>
          <div className="row">
            <button className="btn btn-primary btn-lg" onClick={() => go("demo")}>
              Conversar com a Carol <Icon name="arrow" size={18} />
            </button>
            <button className="btn btn-quiet btn-lg" onClick={() => go("arquitetura")}>
              Como foi feito
            </button>
          </div>
          <p className="fine">Demonstração: dados e sistemas fictícios, modelos de linguagem reais.</p>
        </div>

        <div className="hero-art" aria-label="Colagem de produtos e um exemplo de conversa">
          <img className="tile t-laptop" src="/img/laptop.jpg" alt="Notebook Dell aberto sobre uma superfície branca" />
          <img className="tile t-phones" src="/img/headphones.jpg" alt="Fone de ouvido preto sobre fundo branco" />
          <img className="tile t-phone" src="/img/phone.jpg" alt="Smartphone preto com capa transparente" />
          <img className="tile t-monitor" src="/img/monitor.jpg" alt="Monitor, teclado e mouse em uma mesa branca" />
          <div className="hero-chat" aria-live="polite">
            <div className="bubble bubble-user">{question || " "}</div>
            {question === QUESTION && <div className="bubble bubble-bot">{answer || " "}</div>}
            <div className={`hero-meta ${done ? "show" : ""}`}>
              <Icon name="shield" size={14} /> vendedor · 4 documentos lidos · 0,4 s
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Personas({ go }: Props) {
  const [personas, setPersonas] = useState<Persona[]>([]);

  useEffect(() => {
    api<Persona[]>("/api/personas").then(setPersonas).catch(() => setPersonas([]));
  }, []);

  return (
    <section className="band band-white" id="personas">
      <div className="container">
        <Reveal>
          <div className="section-head">
            <h2>Escolha quem você é</h2>
            <p>O assistente é o mesmo. O que ele mostra e o que ele faz muda com o papel de quem pergunta.</p>
          </div>
        </Reveal>
        <div className="persona-rail" role="list">
          {personas.map((persona) => (
            <button key={persona.id} className="persona-tile" role="listitem" onClick={() => go("demo", persona.id)}>
              <span className="avatar">
                <Avatar persona={persona.id} />
              </span>
              <span className="tile-body">
                <strong>{persona.nome}</strong>
                <span className="tile-role">{persona.titulo}</span>
                <span className="tile-desc">{persona.descricao}</span>
                <span className="tile-meta">
                  {persona.ferramentas.length === 0 ? "sem ferramentas" : `${persona.ferramentas.length} ferramentas`} · {persona.niveis.length}{" "}
                  {persona.niveis.length === 1 ? "nível de dados" : "níveis de dados"}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

const FEATURES = [
  {
    image: "/img/printer.jpg",
    alt: "Impressora multifuncional HP branca e cinza",
    title: "Responde sobre o catálogo",
    text: "A busca une significado e palavra-chave no mesmo banco. Perguntar quais impressoras a loja vende traz a HP DeskJet e a Epson EcoTank, com preço e estoque.",
    cta: "Testar uma pergunta",
    to: "demo" as Tab,
  },
  {
    image: "/img/atendimento.jpg",
    alt: "Atendente sorrindo com fone de headset em uma mesa de trabalho",
    title: "Resolve pedidos de verdade",
    text: "Pede férias, abre ticket de TI e manda mensagem no canal certo. Antes de qualquer ação que muda algo, a Carol mostra o que vai fazer e espera o seu sim.",
    cta: "Ver uma ação com confirmação",
    to: "demo" as Tab,
  },
  {
    image: "/img/monitor.jpg",
    alt: "Monitor com paisagem na tela sobre uma mesa branca",
    title: "Faz conta sem chutar",
    text: "Somas e rankings saem de consultas SQL, não do modelo de linguagem. O resultado bate com a conta feita direto no banco, e há teste para isso.",
    cta: "Ver o ranking de vendedores",
    to: "demo" as Tab,
  },
];

function Features({ go }: Props) {
  return (
    <section className="band band-paper" id="faz">
      <div className="container">
        <Reveal>
          <div className="section-head">
            <h2>O que a Carol faz</h2>
          </div>
        </Reveal>
        <div className="feature-list">
          {FEATURES.map((feature) => (
            <Reveal key={feature.title} className="feature-row">
              <img src={feature.image} alt={feature.alt} loading="lazy" />
              <div className="feature-text">
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
                <button className="link-arrow" onClick={() => go(feature.to)}>
                  {feature.cta} <Icon name="arrow" size={16} />
                </button>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

const SECURITY = [
  "O filtro de acesso roda no banco: o que você não pode ver nem chega ao modelo.",
  "O modelo só enxerga as ferramentas do seu papel, e cada chamada é conferida de novo no servidor.",
  "Mensagens suspeitas são barradas, dados pessoais são redigidos e tudo fica na auditoria.",
  "O app usa um usuário de banco que só lê o negócio e só insere logs: não edita nem apaga.",
];

function Security({ go }: Props) {
  return (
    <section className="band band-ink" id="seguranca">
      <div className="container security-grid">
        <Reveal className="security-copy">
          <h2>Segurança que não depende do prompt</h2>
          <p className="lead-dark">Um ataque de injeção não vaza o que o modelo nunca recebeu. Por isso a permissão fica nas camadas que o modelo não controla.</p>
          <ul className="check-list">
            {SECURITY.map((item) => (
              <li key={item}>
                <Icon name="check" size={18} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <button className="btn btn-light btn-lg" onClick={() => go("lab")}>
            Abrir o laboratório <Icon name="arrow" size={18} />
          </button>
        </Reveal>
        <Reveal className="security-art">
          <ShieldSpot />
        </Reveal>
      </div>
    </section>
  );
}

const EVALUATOR = [
  { tab: "lab" as Tab, title: "Laboratório", text: "Guardrails, roteador, permissões e cache rodando ao vivo, sem custo.", icon: "flask" as const },
  { tab: "arquitetura" as Tab, title: "Como foi feito", text: "O caminho de uma mensagem, as decisões de projeto e o que é simulado.", icon: "blueprint" as const },
  { tab: "metricas" as Tab, title: "Métricas", text: "Rotas, cache, economia do roteamento, ferramentas e bloqueios.", icon: "chart" as const },
];

function Evaluator({ go }: Props) {
  return (
    <section className="band band-white" id="avaliar">
      <div className="container">
        <Reveal>
          <div className="section-head">
            <h2>Para quem avalia</h2>
            <p>Três lugares para ir além da conversa.</p>
          </div>
        </Reveal>
        <Reveal>
          <ul className="row-links">
            {EVALUATOR.map((item) => (
              <li key={item.tab}>
                <button onClick={() => go(item.tab)}>
                  <span className="row-icon">
                    <Icon name={item.icon} size={24} />
                  </span>
                  <span className="row-text">
                    <strong>{item.title}</strong>
                    <span>{item.text}</span>
                  </span>
                  <Icon name="arrow" size={22} className="row-arrow" />
                </button>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </section>
  );
}

function CallToAction({ go }: Props) {
  return (
    <section className="band band-cobalt">
      <div className="container cta-grid">
        <Reveal>
          <h2>Teste agora com a persona que quiser</h2>
          <p className="lead-cobalt">Cada perfil dá respostas diferentes à mesma pergunta. Faça a prova.</p>
        </Reveal>
        <Reveal>
          <button className="btn btn-light btn-lg" onClick={() => go("demo")}>
            Conversar com a Carol <Icon name="arrow" size={18} />
          </button>
        </Reveal>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <Logo onDark size={30} />
          <p className="footer-note">
            AiBites é uma loja fictícia. Produtos, vendedores, vendas, RH, TI e Slack são simulados; o custo exibido é simulado. Os modelos de
            linguagem são reais e gratuitos.
          </p>
        </div>
        <p className="footer-note">
          Fotos de produtos: Unsplash (licença gratuita). Ilustrações, ícones e logo desenhados para este projeto.
        </p>
      </div>
    </footer>
  );
}

export function Home({ go }: Props) {
  return (
    <main>
      <Hero go={go} />
      <Personas go={go} />
      <Features go={go} />
      <Security go={go} />
      <Evaluator go={go} />
      <CallToAction go={go} />
    </main>
  );
}
