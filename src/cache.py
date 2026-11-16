"""Cache semântico das respostas do RAG, no próprio PostgreSQL (pgvector).

Perguntas parecidas ("quais impressoras vocês vendem?" e "que impressoras tem?")
reaproveitam a mesma resposta, sem nova chamada ao modelo. Para isso ser seguro
em um sistema com permissões, o cache segue quatro regras:

1. só guarda respostas montadas com documentos que o papel enxerga **pelo nível**
   (nada que só apareceu por ser "um documento do próprio usuário", como o
   salário dele ou as vendas dele);
2. a chave inclui o conjunto de níveis que o papel enxerga, então a resposta de
   um papel nunca é servida a quem enxerga menos;
3. perguntas na primeira pessoa ("meu salário") nunca entram;
4. cada entrada guarda a versão dos dados e expira (24 h por padrão): mudou o
   banco, o cache antigo deixa de valer.
"""

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from rbac import niveis_permitidos
from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.92
TTL_HOURS = 24
FIRST_PERSON = re.compile(r"\b(meu|minha|meus|minhas|eu|mim|comigo)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CacheHit:
    """Resposta reaproveitada do cache.

    Attributes:
        answer: Texto da resposta guardada.
        similarity: Similaridade (0 a 1) com a pergunta original.
        question: Pergunta que gerou a entrada.
    """

    answer: str
    similarity: float
    question: str


def scope_key(papel: str) -> str:
    """Chave de escopo: os níveis de documento que o papel enxerga."""
    return ",".join(sorted(niveis_permitidos(papel))) or "nenhum"


def is_cacheable(question: str, source_metadatas: Iterable[Mapping[str, Any]], answer: str, papel: str) -> bool:
    """Decide se uma resposta do RAG pode ir para o cache.

    Args:
        question: Pergunta original.
        source_metadatas: Metadados dos documentos usados na resposta.
        answer: Resposta final.
        papel: Papel de quem perguntou.

    Returns:
        `True` só se a pergunta não é pessoal, a resposta não está vazia e todos
        os documentos usados são visíveis ao papel pelo nível (não por serem do próprio usuário).
    """
    if not answer.strip() or FIRST_PERSON.search(question):
        return False

    visiveis = set(niveis_permitidos(papel))
    sources = list(source_metadatas)
    if not sources or not visiveis:
        return False

    return all(meta.get("nivel") in visiveis for meta in sources)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"


def lookup(
    engine: Engine,
    vector: list[float],
    scope: str,
    version: str,
    threshold: float = SIMILARITY_THRESHOLD,
) -> CacheHit | None:
    """Procura uma resposta guardada para uma pergunta parecida.

    Args:
        engine: Conexão (usuário do app).
        vector: Embedding da pergunta.
        scope: Resultado de `scope_key(papel)`.
        version: Versão dos dados (hash do índice).
        threshold: Similaridade mínima de cosseno.

    Returns:
        O `CacheHit` mais parecido acima do limite, ou `None`. Falha de banco = `None`.
    """
    try:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    "SELECT cache_id, resposta, pergunta, 1 - (embedding <=> CAST(:v AS vector)) AS similaridade "
                    "FROM cache_semantico WHERE escopo = :escopo AND versao_indice = :versao AND expira_em > now() "
                    "ORDER BY embedding <=> CAST(:v AS vector) LIMIT 1"
                ),
                {"v": _vector_literal(vector), "escopo": scope, "versao": version},
            ).first()

            if row is None or row.similaridade < threshold:
                return None

            connection.execute(
                text("UPDATE cache_semantico SET acertos = acertos + 1 WHERE cache_id = :id"), {"id": row.cache_id}
            )
            return CacheHit(row.resposta, float(row.similaridade), row.pergunta)
    except Exception:
        logger.exception("Não foi possível consultar o cache semântico.")
        return None


def store(
    engine: Engine,
    vector: list[float],
    scope: str,
    version: str,
    question: str,
    answer: str,
    ttl_hours: float = TTL_HOURS,
) -> None:
    """Guarda uma resposta no cache (falha de banco só vai para o log)."""
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO cache_semantico (expira_em, escopo, versao_indice, pergunta, embedding, resposta) "
                    "VALUES (now() + make_interval(hours => :ttl), :escopo, :versao, :pergunta, "
                    "CAST(:v AS vector), :resposta)"
                ),
                {
                    "ttl": ttl_hours,
                    "escopo": scope,
                    "versao": version,
                    "pergunta": question[:1000],
                    "v": _vector_literal(vector),
                    "resposta": answer,
                },
            )
    except Exception:
        logger.exception("Não foi possível gravar no cache semântico.")
