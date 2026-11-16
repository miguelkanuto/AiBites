"""Quem pode usar cada ferramenta do agente (política única, sem dependências pesadas).

O app (host) usa esta política para decidir quais ferramentas o modelo chega a
ver e para barrar chamadas indevidas; os servidores MCP a usam de novo ao
executar. Assim a permissão não depende de o modelo "se comportar".

Nomes têm o formato `servidor.ferramenta`.
"""

from dataclasses import dataclass

FUNCIONARIOS = frozenset({"vendedor", "ti", "gerente_vendas", "rh", "ceo"})
VENDAS = frozenset({"vendedor", "gerente_vendas", "ceo"})
GESTAO = frozenset({"gerente_vendas", "ceo"})


@dataclass(frozen=True)
class ToolPolicy:
    """Regra de uma ferramenta.

    Attributes:
        papeis: Papéis que podem usá-la.
        escreve: `True` se a ferramenta muda algo (exige confirmação do usuário).
        resumo: Texto da confirmação, com `{campos}` dos argumentos.
    """

    papeis: frozenset[str]
    escreve: bool = False
    resumo: str = ""


FERRAMENTAS: dict[str, ToolPolicy] = {
    "rh.consultar_saldo_ferias": ToolPolicy(FUNCIONARIOS),
    "rh.listar_solicitacoes_ferias": ToolPolicy(FUNCIONARIOS),
    "rh.solicitar_ferias": ToolPolicy(
        FUNCIONARIOS,
        escreve=True,
        resumo="Pedir férias de {data_inicio} a {data_fim}",
    ),
    "ti.listar_meus_tickets": ToolPolicy(FUNCIONARIOS),
    "ti.consultar_ticket": ToolPolicy(FUNCIONARIOS),
    "ti.listar_fila": ToolPolicy(frozenset({"ti", "ceo"})),
    "ti.abrir_ticket": ToolPolicy(
        FUNCIONARIOS,
        escreve=True,
        resumo="Abrir ticket de TI «{titulo}» (prioridade {prioridade}, categoria {categoria})",
    ),
    "slack.listar_canais": ToolPolicy(FUNCIONARIOS),
    "slack.enviar_mensagem": ToolPolicy(
        FUNCIONARIOS,
        escreve=True,
        resumo="Enviar no canal {canal} a mensagem: «{texto}»",
    ),
    "vendas.total_vendido": ToolPolicy(VENDAS),
    "vendas.ranking_vendedores": ToolPolicy(GESTAO),
    "vendas.total_por_categoria": ToolPolicy(VENDAS),
}

# Canais do Slack fictício e quem pode postar em cada um.
CANAIS: dict[str, frozenset[str]] = {
    "#geral": FUNCIONARIOS,
    "#vendas": VENDAS,
    "#ti": FUNCIONARIOS,
    "#rh": FUNCIONARIOS,
    "#diretoria": frozenset({"ceo"}),
}


def pode_usar(papel: str, ferramenta: str) -> bool:
    """`True` se o papel pode usar a ferramenta (desconhecida ou papel inválido: não)."""
    politica = FERRAMENTAS.get(ferramenta)
    return politica is not None and papel in politica.papeis


def ferramentas_permitidas(papel: str) -> list[str]:
    """Nomes das ferramentas que o papel enxerga, em ordem estável."""
    return sorted(nome for nome in FERRAMENTAS if pode_usar(papel, nome))


def canais_permitidos(papel: str) -> list[str]:
    """Canais do Slack em que o papel pode postar."""
    return sorted(canal for canal, papeis in CANAIS.items() if papel in papeis)


def exige_confirmacao(ferramenta: str) -> bool:
    """`True` para ferramentas que alteram algo."""
    politica = FERRAMENTAS.get(ferramenta)
    return bool(politica and politica.escreve)


def resumir(ferramenta: str, argumentos: dict) -> str:
    """Texto curto da ação, para o usuário confirmar (campos ausentes viram «?»)."""
    politica = FERRAMENTAS.get(ferramenta)
    modelo = politica.resumo if politica and politica.resumo else ferramenta

    class _Padrao(dict):
        def __missing__(self, chave: str) -> str:
            return "?"

    return modelo.format_map(_Padrao(argumentos))
