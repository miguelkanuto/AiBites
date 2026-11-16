import { useEffect, useState } from "react";
import { api, percent, usd } from "../api";

type MetricsData = {
  janela_dias: number;
  mensagens: number;
  custo_simulado: number;
  custo_se_tudo_fosse_forte: number;
  economia: number;
  por_rota: { rota: string; mensagens: number; latencia_media_ms: number; custo: number; custo_referencia: number; acertos_de_cache: number }[];
  ferramentas: { status: string; chamadas: number }[];
  seguranca: { evento: string; ocorrencias: number }[];
};

const EVENT_LABEL: Record<string, string> = {
  mensagem_bloqueada: "mensagens bloqueadas",
  limite_excedido: "limites de mensagens",
  usuario_pausado: "usuários pausados",
  login_bloqueado: "logins bloqueados",
};

export function Metrics() {
  const [data, setData] = useState<MetricsData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MetricsData>("/api/metrics").then(setData).catch(() => setError("Não foi possível ler as métricas agora."));
  }, []);

  if (error) return <div className="container page"><div className="notice">{error}</div></div>;
  if (!data) return <div className="container page muted">Carregando…</div>;

  const max = Math.max(1, ...data.por_rota.map((r) => r.mensagens));

  return (
    <div className="container page stack">
      <div className="page-head">
        <h1>Métricas</h1>
        <p>
          Números agregados da auditoria dos últimos {data.janela_dias} dias, de todos os visitantes e do chat. Não há dados pessoais aqui. O
          custo é simulado; as respostas só entram na conta de economia depois que passaram a registrar o custo de referência.
        </p>
      </div>

      <div className="grid3">
        <div className="card"><h4>Mensagens</h4><h2>{data.mensagens}</h2></div>
        <div className="card"><h4>Custo simulado</h4><h2>{usd(data.custo_simulado)}</h2><div className="muted small">se tudo fosse no modelo forte: {usd(data.custo_se_tudo_fosse_forte)}</div></div>
        <div className="card"><h4>Economia do roteamento</h4><h2>{percent(data.economia)}</h2></div>
      </div>

      <div className="grid2" style={{ alignItems: "start" }}>
        <div className="card">
          <h3>Por rota</h3>
          <table>
            <thead><tr><th>Rota</th><th>Mensagens</th><th></th><th>Latência</th><th>Cache</th></tr></thead>
            <tbody>
              {data.por_rota.map((row) => (
                <tr key={row.rota}>
                  <td className="mono">{row.rota}</td>
                  <td>{row.mensagens}</td>
                  <td style={{ width: "35%" }}><div className="bar"><span style={{ width: `${(row.mensagens / max) * 100}%` }} /></div></td>
                  <td>{row.latencia_media_ms} ms</td>
                  <td>{row.acertos_de_cache}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="stack">
          <div className="card">
            <h3>Ferramentas do agente</h3>
            {data.ferramentas.length === 0 ? <p className="muted small">Nenhuma chamada ainda.</p> : (
              <div className="row">{data.ferramentas.map((t) => <span className="chip" key={t.status}>{t.status}: {t.chamadas}</span>)}</div>
            )}
          </div>
          <div className="card">
            <h3>Segurança</h3>
            {data.seguranca.length === 0 ? <p className="muted small">Nenhum evento ainda.</p> : (
              <div className="row">{data.seguranca.map((e) => <span className="chip bad" key={e.evento}>{EVENT_LABEL[e.evento] ?? e.evento}: {e.ocorrencias}</span>)}</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
