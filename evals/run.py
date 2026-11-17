"""Avaliação do assistente contra uma instância em execução (local ou publicada).

Uso:
    uv run python evals/run.py --url http://localhost:8001
    uv run python evals/run.py --url https://rag-ex.onrender.com --pausa 2

Cada caso usa uma sessão nova (limites e auditoria são por visitante). Ações que mudam algo
são sempre RECUSADAS na confirmação, então a avaliação não cria ticket, férias nem mensagem.
Sai com código 1 se alguma categoria ficar abaixo do limiar (gate de release).
Chama o LLM de verdade: gasta a cota gratuita do OpenRouter e do Gemini.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

CASOS = Path(__file__).with_name("casos.json")
RELATORIO = Path(__file__).with_name("relatorio.json")


def ler_sse(resposta: httpx.Response, cliente: httpx.Client, recusar: bool) -> dict:
    """Lê o fluxo SSE de /api/chat e devolve o resultado final e os eventos relevantes."""
    evento, resultado = "", {"confirmacao": False, "erro": ""}
    for linha in resposta.iter_lines():
        if linha.startswith("event:"):
            evento = linha.split(":", 1)[1].strip()
        elif linha.startswith("data:"):
            dados = json.loads(linha.split(":", 1)[1])
            if evento == "confirm":
                resultado["confirmacao"] = True
                cliente.post("/api/confirm", json={"id": dados["id"], "ok": not recusar})
            elif evento == "answer":
                resultado.update(dados)
            elif evento == "error":
                resultado["erro"] = dados.get("mensagem", "erro")
    return resultado


def executar(base: str, caso: dict, timeout: float) -> dict:
    inicio = time.perf_counter()
    with httpx.Client(base_url=base, timeout=timeout) as cliente:
        cliente.post("/api/session", json={"persona_id": caso["persona"]}).raise_for_status()
        with cliente.stream("POST", "/api/chat", json={"message": caso["pergunta"]}) as resposta:
            if resposta.status_code != 200:
                return {"erro": f"HTTP {resposta.status_code}", "tempo_ms": 0}
            resultado = ler_sse(resposta, cliente, recusar=caso.get("recusar_confirmacao", True))
    resultado["tempo_ms"] = int((time.perf_counter() - inicio) * 1000)
    return resultado


def avaliar(caso: dict, r: dict) -> list[str]:
    """Devolve a lista de falhas (vazia = passou)."""
    espera = caso["espera"]
    falhas: list[str] = []
    if r.get("erro"):
        return [f"erro: {r['erro']}"]
    resposta = r.get("resposta", "")
    fontes = r.get("fontes", [])
    ferramentas = [f["nome"] for f in r.get("ferramentas", [])]
    if "rota" in espera and r.get("rota") != espera["rota"]:
        falhas.append(f"rota {r.get('rota')} != {espera['rota']}")
    if "bloqueada" in espera and r.get("bloqueada") != espera["bloqueada"]:
        falhas.append(f"bloqueada={r.get('bloqueada')}")
    if "confirmacao" in espera and r.get("confirmacao") != espera["confirmacao"]:
        falhas.append("não pediu confirmação" if espera["confirmacao"] else "pediu confirmação")
    for texto in espera.get("resposta_nao_contem", []):
        if texto.lower() in resposta.lower():
            falhas.append(f"resposta contém '{texto}'")
    if "resposta_contem_qualquer" in espera and not any(t.lower() in resposta.lower() for t in espera["resposta_contem_qualquer"]):
        falhas.append(f"resposta sem nenhum de {espera['resposta_contem_qualquer']}")
    for fonte in espera.get("fontes_nao_contem", []):
        if fonte in fontes:
            falhas.append(f"fonte indevida {fonte}")
    for prefixo in espera.get("fontes_nao_prefixo", []):
        if any(f.startswith(prefixo) for f in fontes):
            falhas.append(f"fonte com prefixo '{prefixo}'")
    for prefixo in espera.get("fontes_contem_prefixo", []):
        if not any(f.startswith(prefixo) for f in fontes):
            falhas.append(f"sem fonte '{prefixo}'")
    for nome in espera.get("ferramentas_contem", []):
        if nome not in ferramentas:
            falhas.append(f"ferramenta {nome} não usada")
    for nome in espera.get("ferramentas_nao", []):
        if nome in ferramentas:
            falhas.append(f"ferramenta proibida {nome}")
    return falhas


def percentil(valores: list[int], p: float) -> int:
    if not valores:
        return 0
    ordenado = sorted(valores)
    return ordenado[min(len(ordenado) - 1, int(round(p * (len(ordenado) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://localhost:8001")
    parser.add_argument("--pausa", type=float, default=1.0, help="segundos entre casos (cota gratuita)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--so", default="", help="roda só uma categoria")
    args = parser.parse_args()

    dados = json.loads(CASOS.read_text(encoding="utf-8"))
    casos = [c for c in dados["casos"] if not args.so or c["categoria"] == args.so]
    por_categoria: dict[str, list[bool]] = {}
    linhas, tempos, economias = [], [], []

    for caso in casos:
        try:
            r = executar(args.url, caso, args.timeout)
        except httpx.HTTPError as erro:
            r = {"erro": type(erro).__name__}
        falhas = avaliar(caso, r)
        por_categoria.setdefault(caso["categoria"], []).append(not falhas)
        if r.get("tempo_ms"):
            tempos.append(r["tempo_ms"])
        if r.get("custo_referencia"):
            economias.append(r.get("economia", 0.0))
        linhas.append({"id": caso["id"], "passou": not falhas, "falhas": falhas, "rota": r.get("rota"), "modelo": r.get("modelo"), "tempo_ms": r.get("tempo_ms")})
        print(f"{'OK  ' if not falhas else 'FALHA'} {caso['id']:8} {r.get('rota', '-'):10} {r.get('tempo_ms', 0):6} ms  {'; '.join(falhas)}")
        time.sleep(args.pausa)

    print("\nCategoria     passou/total  taxa   limiar")
    reprovadas = []
    for categoria, resultados in por_categoria.items():
        taxa = sum(resultados) / len(resultados)
        limiar = dados["limiares"].get(categoria, 1.0)
        if taxa < limiar:
            reprovadas.append(categoria)
        print(f"{categoria:12}  {sum(resultados):3}/{len(resultados):<3}       {taxa:5.0%}  {limiar:5.0%}  {'REPROVADA' if taxa < limiar else 'ok'}")

    resumo = {
        "casos": len(linhas),
        "latencia_p50_ms": int(statistics.median(tempos)) if tempos else 0,
        "latencia_p95_ms": percentil(tempos, 0.95),
        "economia_media_do_roteamento": round(statistics.mean(economias), 4) if economias else 0.0,
        "categorias_reprovadas": reprovadas,
    }
    print(f"\nLatência p50 {resumo['latencia_p50_ms']} ms, p95 {resumo['latencia_p95_ms']} ms; economia média simulada {resumo['economia_media_do_roteamento']:.0%}")
    RELATORIO.write_text(json.dumps({"resumo": resumo, "casos": linhas}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("GATE:", "REPROVADO" if reprovadas else "APROVADO")
    return 1 if reprovadas else 0


if __name__ == "__main__":
    sys.exit(main())
