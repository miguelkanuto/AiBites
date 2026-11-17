"""Roteador de modelos: decide para onde cada mensagem vai e quanto isso custa.

Rotas (da mais barata para a mais cara):
- `smalltalk`: cumprimentos e agradecimentos. Resposta pronta, sem modelo (custo zero).
- `rag`: consulta de produtos, vendedores e vendas. Faixa padrão.
- `agent`: ações (férias, ticket, mensagem) e contas exatas (somas, rankings). Faixa forte.

É um conjunto de regras, previsível e sem custo; o texto já chega normalizado.
"""

import re
from dataclasses import dataclass

from guardrails import normalize

SMALLTALK = re.compile(
    # Cumprimento, opcionalmente com uma frase de cortesia; ou agradecimento/despedida.
    # Frases livres depois do cumprimento ("oi, quanto vendi?") NÃO são conversa fiada.
    r"^((oi+|ola+|opa|e ai|bom dia|boa tarde|boa noite)[,!. ]*"
    r"(tudo (bem|bom|certo)|td bem|pessoal|gente|time|equipe|carol|a todos)?"
    r"|tudo (bem|bom|certo)"
    r"|ok|certo|beleza|blz|tchau|ate (mais|logo)"
    r")[,!.? ]*$"
    r"|^(muito )?(obrigad[oa]|valeu|vlw|brigad[oa])[^?]{0,30}$"
)

AGENT_RULES = (
    ("férias", r"\b(ferias|saldo de ferias)\b"),
    ("ticket de TI", r"\b(ticket|tickets|chamado|chamados)\b"),
    ("código de chamado ou pedido", r"\bti-\d+\b|\bfer-\d{4}-\d+\b"),
    ("enviar mensagem", r"\b(enviar|envie|manda|mande|mandar|escreva|avise|avisar|poste|postar)\b.{0,30}\b(mensagem|recado|aviso|canal)\b"),
    ("Slack ou canal", r"\b(slack|canal)\b"),
    ("quanto vendeu", r"\bquanto\b.{0,25}\b(vend|fatur|arrecad)"),
    ("soma ou ranking de vendas", r"\b(total|soma|somar|media|ranking|faturamento|faturou|ticket medio)\b.{0,40}\b(vend|venda|vendas|vendido|vendedor|vendedores|categoria|regiao|mes)\b"),
    ("melhor ou maior vendedor", r"\b(maior|maiores|melhor|melhores|pior|piores|top)\b.{0,15}\b(vendedor|vendedora|vendedores)\b"),
    ("contagem de vendas", r"\bquantas vendas\b|\bquantas unidades\b"),
    # "já vendemos algum celular?", "quantos notebooks foram vendidos?": contagem exata, não texto da base.
    ("contagem de itens vendidos", r"\bquantos?\b.{0,40}\b(vendemos|vendeu|vendeu-se|vendido|vendidos|vendida|vendidas|vendi)\b|\bja\b.{0,15}\b(vendemos|vendeu|vendi)\b"),
)
_AGENT = tuple((label, re.compile(pattern)) for label, pattern in AGENT_RULES)


@dataclass(frozen=True)
class Route:
    """Decisão do roteador.

    Attributes:
        name: `smalltalk`, `rag` ou `agent`.
        tier: Faixa de modelo: `none`, `standard` ou `strong`.
        reason: Regra que decidiu (para o log).
    """

    name: str
    tier: str
    reason: str


def route(message: str, continuing_agent: bool = False) -> Route:
    """Escolhe a rota da mensagem.

    Args:
        message: Texto digitado pelo usuário.
        continuing_agent: `True` quando a última resposta do agente foi uma pergunta;
            a resposta do usuário continua a conversa com o agente.

    Returns:
        A `Route` escolhida; na dúvida, `rag` (a rota que só lê).
    """
    plain = normalize(message)

    if continuing_agent and not SMALLTALK.match(plain):
        return Route("agent", "strong", "continuação do agente")

    if SMALLTALK.match(plain):
        return Route("smalltalk", "none", "cumprimento ou agradecimento")

    for label, pattern in _AGENT:
        if pattern.search(plain):
            return Route("agent", "strong", label)

    return Route("rag", "standard", "consulta à base")


SMALLTALK_REPLIES = {
    "obrigad": "De nada! Se precisar de mais alguma coisa, é só chamar.",
    "brigad": "De nada! Se precisar de mais alguma coisa, é só chamar.",
    "valeu": "Por nada! Qualquer coisa, estou por aqui.",
    "vlw": "Por nada! Qualquer coisa, estou por aqui.",
    "tchau": "Até mais!",
    "ate ": "Até mais!",
}


def smalltalk_reply(message: str, first_name: str) -> str:
    """Resposta pronta (sem modelo) para cumprimentos, agradecimentos e despedidas."""
    plain = normalize(message)
    for key, reply in SMALLTALK_REPLIES.items():
        if plain.startswith(key):
            return reply
    return f"Oi, {first_name}! Em que posso ajudar com produtos, vendas, férias ou tickets?"
