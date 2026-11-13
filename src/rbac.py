"""Controle de acesso por papel (RBAC) para o RAG da AiBites.

Cada documento indexado carrega um `nivel` de sensibilidade e, quando tem dono,
um `dono` (id do funcionário). A regra é aplicada em dois pontos:

1. como filtro na consulta ao banco vetorial, antes do modelo ver qualquer texto;
2. como checagem final nos resultados (`filtrar_resultados`), por segurança.

Este módulo não importa nada pesado, para os testes da política rodarem rápido.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

NIVEIS = ("publico", "interno", "vendas", "rh", "diretoria")

# Níveis que cada papel enxerga. Papel desconhecido não enxerga nada.
NIVEIS_POR_PAPEL: dict[str, tuple[str, ...]] = {
    "cliente": ("publico",),
    "vendedor": ("publico", "interno"),
    "ti": ("publico", "interno"),
    "gerente_vendas": ("publico", "interno", "vendas"),
    "rh": ("publico", "interno", "rh"),
    "ceo": NIVEIS,
}

# Nível que não casa com nenhum documento (usado para papel desconhecido).
NIVEL_NENHUM = "__nenhum__"


@dataclass(frozen=True)
class Usuario:
    """Quem está falando com a Carol.

    Attributes:
        usuario_id: Identificador do login.
        nome: Nome para exibição.
        papel: Papel de acesso (chave de `NIVEIS_POR_PAPEL`).
        funcionario_id: Id do funcionário, quando o usuário é da empresa.
        cliente_id: Id do cliente, quando o usuário é externo.
    """

    usuario_id: str
    nome: str
    papel: str
    funcionario_id: str | None = None
    cliente_id: str | None = None

    @property
    def dono_id(self) -> str | None:
        """Id usado na regra "ver os próprios documentos" (só funcionários)."""
        return self.funcionario_id

    def to_metadata(self) -> dict[str, Any]:
        """Dados guardados na sessão de login do Chainlit."""
        return {
            "usuario_id": self.usuario_id,
            "nome": self.nome,
            "papel": self.papel,
            "funcionario_id": self.funcionario_id,
            "cliente_id": self.cliente_id,
        }

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "Usuario":
        """Reconstrói o usuário a partir dos dados da sessão."""
        return cls(
            usuario_id=str(metadata["usuario_id"]),
            nome=str(metadata["nome"]),
            papel=str(metadata["papel"]),
            funcionario_id=metadata.get("funcionario_id"),
            cliente_id=metadata.get("cliente_id"),
        )


def niveis_permitidos(papel: str) -> tuple[str, ...]:
    """Níveis de documento que o papel pode ver (vazio se o papel não existe)."""
    return NIVEIS_POR_PAPEL.get(papel, ())


def pode_ver(usuario: Usuario, metadata: Mapping[str, Any]) -> bool:
    """Decide se o usuário pode ver um documento, pelos metadados dele.

    Documento sem `nivel` é tratado como restrito (negado).

    Args:
        usuario: Quem está consultando.
        metadata: Metadados do documento (`nivel` e, opcionalmente, `dono`).

    Returns:
        `True` quando o nível é permitido ao papel ou o documento é do próprio usuário.
    """
    nivel = metadata.get("nivel")
    if nivel is None or usuario.papel not in NIVEIS_POR_PAPEL:
        return False

    if nivel in niveis_permitidos(usuario.papel):
        return True

    dono = metadata.get("dono")
    return dono is not None and dono == usuario.dono_id


def filtrar_resultados(usuario: Usuario, nodes: Iterable[Any]) -> list[Any]:
    """Descarta resultados da busca que o usuário não pode ver (segunda barreira).

    Args:
        usuario: Quem está consultando.
        nodes: Itens do LlamaIndex (`NodeWithScore`), que expõem `.metadata`.

    Returns:
        Somente os itens permitidos.
    """
    return [node for node in nodes if pode_ver(usuario, node.metadata)]


def build_access_filters(usuario: Usuario):
    """Monta o filtro de metadados do LlamaIndex para o usuário.

    O filtro vira condição SQL no pgvector: documentos fora da regra nem chegam
    ao Python, quanto mais ao modelo.

    Args:
        usuario: Quem está consultando.

    Returns:
        `MetadataFilters` com "nível permitido OU documento próprio".
    """
    from llama_index.core.vector_stores import (
        FilterCondition,
        FilterOperator,
        MetadataFilter,
        MetadataFilters,
    )

    niveis = list(niveis_permitidos(usuario.papel)) or [NIVEL_NENHUM]
    regras: list[Any] = [
        MetadataFilter(key="nivel", value=niveis, operator=FilterOperator.IN)
    ]

    if usuario.dono_id and niveis_permitidos(usuario.papel):
        regras.append(
            MetadataFilter(key="dono", value=usuario.dono_id, operator=FilterOperator.EQ)
        )

    return MetadataFilters(filters=regras, condition=FilterCondition.OR)
