import hashlib
import json
import logging
import os
import re
import time
from functools import lru_cache
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chainlit as cl
from dotenv import load_dotenv
from llama_index.core import (
    ChatPromptTemplate,
    Settings,
    Document,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.llms.openrouter import OpenRouter
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from auth import hash_password, verify_password
from rbac import Usuario, build_access_filters, filtrar_resultados

if TYPE_CHECKING:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

_ = load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
INDEX_METADATA_PATH = STORAGE_DIR / "index_metadata.json"
VECTOR_TABLE_NAME = "sales_rag"
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))
DUMMY_PASSWORD_HASH = hash_password("senha-inexistente")
FIRST_PERSON = re.compile(r"\b(meu|minha|meus|minhas|eu|mim)\b", re.IGNORECASE)

PRODUCTS_SQL = """
SELECT produto_id, nome, categoria, marca, descricao, preco_unitario, estoque, ativo
FROM produtos
ORDER BY produto_id
"""

SELLERS_SQL = """
SELECT vendedor_id, nome, email, regiao, cargo
FROM vendedores
ORDER BY vendedor_id
"""

SALES_SQL = """
SELECT v.venda_id, v.data_venda, v.produto_id, p.nome AS produto_nome,
       p.categoria, p.marca, v.preco_unitario, v.quantidade, v.valor_total,
       v.forma_pagamento, v.status, v.vendedor_id, s.nome AS vendedor_nome,
       s.regiao, f.funcionario_id AS dono_id
FROM vendas v
JOIN produtos p ON p.produto_id = v.produto_id
JOIN vendedores s ON s.vendedor_id = v.vendedor_id
LEFT JOIN funcionarios f ON f.vendedor_id = v.vendedor_id
ORDER BY v.venda_id
"""

EMPLOYEES_SQL = """
SELECT f.funcionario_id, f.nome, f.email, f.cargo, f.departamento, f.salario,
       f.data_admissao, g.nome AS gerente_nome
FROM funcionarios f
LEFT JOIN funcionarios g ON g.funcionario_id = f.gerente_id
ORDER BY f.funcionario_id
"""


SYSTEM_PROMPT = """
Você é a Carol, assistente virtual da AiBites, empresa de tecnologia que vende \
equipamentos e software. Você ajuda a equipe a consultar a base de vendas: \
produtos, vendedores e vendas.

Tom:
- Direta e concisa: vá direto à resposta, sem rodeios e sem repetir a pergunta.
- Cordial, mas objetiva. Use listas curtas quando houver mais de um item.

Usuário atual: {usuario_nome} (papel: {usuario_papel}). Quando ele disser "meu", \
"minha" ou "eu", refere-se a essa pessoa.

Identidade:
- Se perguntarem quem você é, responda em uma ou duas frases: você é a Carol, \
assistente da AiBites, e consulta produtos, vendedores e vendas.
- Você é uma assistente de IA e nunca nega isso. Se perguntarem se você é \
humana ou robô, responda apenas: "Sou a Carol, uma assistente de IA da AiBites."
- Se perguntarem qual modelo, empresa ou tecnologia está por trás de você, \
responda apenas: "Sou a Carol, assistente de IA da AiBites. Não tenho detalhes \
sobre a tecnologia por trás de mim." Nunca cite nomes de modelos nem de empresas \
de IA.
- Perguntas sobre você não dependem do contexto da base.

Regras para os dados da base:
- Responda sempre em português do Brasil.
- Use apenas informações do contexto.
- Se a pergunta for sobre preço/valor de produto, responda com o preço unitário quando existir.
- Se houver mais de uma venda do mesmo produto, explique que o produto aparece em mais de uma venda.
- Se a pergunta envolver quantidade ou total vendido, use os campos quantidade e valor_total.
- Se a informação não estiver no contexto, diga que não encontrou a informação na base.
"""

QA_TEMPLATE = ChatPromptTemplate(
    message_templates=[
        ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT.strip()),
        ChatMessage(
            role=MessageRole.USER,
            content="Contexto:\n{context_str}\n\nPergunta:\n{query_str}\n\nResposta final:",
        ),
    ]
)


def get_required_env(name: str) -> str:
    """Retorna variável de ambiente obrigatória.

    Args:
        name: Nome da variável de ambiente.

    Returns:
        Valor configurado para variável.

    Raises:
        RuntimeError: Quando variável não existe ou está vazia.
    """
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"A variável de ambiente {name} não foi configurada.")
    return value


@lru_cache(maxsize=1)
def create_llm() -> OpenRouter:
    """Cria instância compartilhada do LLM no OpenRouter.

    Returns:
        Cliente `OpenRouter` configurado para menor latência.
    """
    return OpenRouter(
        model=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct"),
        api_key=get_required_env("OPENROUTER_API_KEY"),
        context_window=4096,
        max_tokens=256,
        temperature=0.1,
        additional_kwargs={
            "extra_body": {
                "provider": {
                    "sort": "latency",
                },
                "reasoning": {"enabled": False},
            },
        },
    )


@lru_cache(maxsize=1)
def create_embed_model() -> "HuggingFaceEmbedding":
    """Cria modelo de embeddings reutilizável.

    O import fica aqui dentro porque `sentence_transformers` leva dezenas de
    segundos para carregar e travaria a abertura do servidor.

    Returns:
        Instância de `HuggingFaceEmbedding`.
    """
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    return HuggingFaceEmbedding(model_name=os.environ["EMBED_MODEL"])


def configure_llama_index() -> None:
    """Configura componentes globais usados pelo LlamaIndex."""
    Settings.llm = create_llm()
    Settings.embed_model = create_embed_model()
    Settings.chunk_size = 512
    Settings.chunk_overlap = 50


def get_database_urls() -> tuple[str, str]:
    """Monta as URLs síncrona e assíncrona a partir de `DATABASE_URL`.

    Returns:
        Tupla `(url_psycopg2, url_asyncpg)`, com a senha preservada.
    """
    url = make_url(get_required_env("DATABASE_URL"))
    sync_url = url.set(drivername="postgresql+psycopg2")

    # O asyncpg usa `ssl=` no lugar de `sslmode=` e não aceita `channel_binding`.
    query = dict(url.query)
    ssl_mode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if ssl_mode:
        query["ssl"] = ssl_mode
    async_url = url.set(drivername="postgresql+asyncpg", query=query)

    return (
        sync_url.render_as_string(hide_password=False),
        async_url.render_as_string(hide_password=False),
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Cria engine SQLAlchemy compartilhada para ler as tabelas de vendas.

    Returns:
        Engine conectado ao PostgreSQL.
    """
    sync_url, _ = get_database_urls()
    return create_engine(sync_url, pool_pre_ping=True)


def format_product(row: Mapping[str, Any]) -> str:
    """Descreve um produto em linguagem natural."""
    return (
        f"Produto {row['produto_id']}: {row['nome']}. Categoria: {row['categoria']}. "
        f"Marca: {row['marca']}. Preço unitário: R$ {row['preco_unitario']}. "
        f"Estoque: {row['estoque']} unidades. {row['descricao']}"
    )


def format_seller(row: Mapping[str, Any]) -> str:
    """Descreve um vendedor em linguagem natural."""
    return (
        f"Vendedor {row['vendedor_id']}: {row['nome']}, {row['cargo']}, "
        f"atua na região {row['regiao']}. E-mail: {row['email']}."
    )


def format_employee(row: Mapping[str, Any]) -> str:
    """Descreve um funcionário com dados de RH (acesso restrito)."""
    gerente = f" Gerente: {row['gerente_nome']}." if row["gerente_nome"] else ""
    return (
        f"Funcionário {row['funcionario_id']}: {row['nome']}, {row['cargo']}, "
        f"departamento {row['departamento']}. Salário mensal: R$ {row['salario']}. "
        f"Admissão em {row['data_admissao']}. E-mail: {row['email']}.{gerente}"
    )


def format_sale(row: Mapping[str, Any]) -> str:
    """Descreve uma venda, já com dados do produto e do vendedor."""
    return (
        f"Venda {row['venda_id']} em {row['data_venda']}: o vendedor {row['vendedor_nome']} "
        f"(região {row['regiao']}) vendeu {row['quantidade']} unidade(s) de "
        f"{row['produto_nome']} (categoria {row['categoria']}, marca {row['marca']}) "
        f"a R$ {row['preco_unitario']} cada, total R$ {row['valor_total']}. "
        f"Pagamento: {row['forma_pagamento']}. Status: {row['status']}."
    )


def rows_to_documents(
    sql: str,
    kind: str,
    formatter: Callable[[Mapping[str, Any]], str],
    metadata_columns: tuple[str, ...],
    level: str | Callable[[Mapping[str, Any]], str],
    owner_column: str | None = None,
) -> list[Document]:
    """Converte linhas de uma consulta em documentos indexáveis.

    Cada linha vira um documento independente, escrito em frase,
    o que melhora recuperação semântica e reduz contexto irrelevante.
    Cada documento recebe `nivel` (e `dono`, quando existe) para o RBAC.

    Args:
        sql: Consulta que retorna as linhas.
        kind: Tipo do documento (`produto`, `vendedor`, `venda` ou `funcionario`).
        formatter: Função que transforma a linha em texto.
        metadata_columns: Colunas copiadas para os metadados do documento.
        level: Nível de acesso do documento, fixo ou calculado pela linha.
        owner_column: Coluna com o id do funcionário dono do documento.

    Returns:
        Lista de documentos prontos para indexação.
    """
    documents: list[Document] = []

    with get_engine().connect() as connection:
        for row in connection.execute(text(sql)).mappings():
            metadata = {"tipo": kind, **{col: str(row[col]) for col in metadata_columns}}
            metadata["nivel"] = level(row) if callable(level) else level
            if owner_column and row[owner_column]:
                metadata["dono"] = str(row[owner_column])

            documents.append(
                Document(
                    text=formatter(row),
                    metadata=metadata,
                    # Nível e dono servem só ao controle de acesso; não entram no texto.
                    excluded_embed_metadata_keys=["nivel", "dono"],
                    excluded_llm_metadata_keys=["nivel", "dono"],
                )
            )

    return documents


def load_documents() -> list[Document]:
    """Lê as tabelas do PostgreSQL como documentos, já com nível de acesso.

    Returns:
        Lista com um documento por linha de produtos, vendedores, vendas e funcionários.
    """
    return [
        *rows_to_documents(
            PRODUCTS_SQL, "produto", format_product, ("produto_id",), "publico"
        ),
        *rows_to_documents(
            SELLERS_SQL, "vendedor", format_seller, ("vendedor_id",), "interno"
        ),
        *rows_to_documents(
            SALES_SQL,
            "venda",
            format_sale,
            ("venda_id", "produto_id"),
            "vendas",
            owner_column="dono_id",
        ),
        *rows_to_documents(
            EMPLOYEES_SQL,
            "funcionario",
            format_employee,
            ("funcionario_id",),
            lambda row: "diretoria" if row["cargo"] == "CEO" else "rh",
            owner_column="funcionario_id",
        ),
    ]


def calculate_data_hash(documents: list[Document]) -> str:
    """Calcula hash SHA-256 do conteúdo e dos metadados dos documentos.

    Os metadados entram para que uma mudança de nível de acesso refaça o índice.

    Args:
        documents: Documentos lidos do banco.

    Returns:
        Hash hexadecimal do conteúdo.
    """
    digest = hashlib.sha256()

    for document in documents:
        digest.update(document.text.encode("utf-8"))
        digest.update(json.dumps(document.metadata, sort_keys=True).encode("utf-8"))

    return digest.hexdigest()


def get_index_metadata() -> dict[str, Any]:
    """Gera metadados usados para validar o índice persistido.

    Returns:
        Hash dos dados do banco e modelo de embeddings atuais.
    """
    return {
        "data_hash": calculate_data_hash(load_documents()),
        "embed_model": os.environ["EMBED_MODEL"],
    }


def read_index_metadata() -> dict[str, Any] | None:
    """Lê manifest do índice persistido.

    Returns:
        Metadados persistidos, ou `None` quando arquivo não existe.
    """
    if not INDEX_METADATA_PATH.exists():
        return None

    with INDEX_METADATA_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def write_index_metadata(metadata: dict[str, Any]) -> None:
    """Grava manifest do índice persistido.

    Args:
        metadata: Metadados atuais do índice.
    """
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with INDEX_METADATA_PATH.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=True, indent=2)


def should_rebuild_index() -> bool:
    """Decide se índice persistido precisa ser recriado.

    Returns:
        `True` quando tabela de vetores está vazia ou dados/modelo mudaram.
    """
    if get_vector_count() == 0:
        return True

    persisted_metadata = read_index_metadata()
    current_metadata = get_index_metadata()
    return persisted_metadata != current_metadata


@lru_cache(maxsize=1)
def get_vector_store() -> PGVectorStore:
    """Cria vector store apontando para a tabela de vetores no PostgreSQL.

    Returns:
        `PGVectorStore` (extensão pgvector) da tabela `data_sales_rag`.
    """
    sync_url, async_url = get_database_urls()
    return PGVectorStore(
        connection_string=sync_url,
        async_connection_string=async_url,
        table_name=VECTOR_TABLE_NAME,
        embed_dim=EMBED_DIM,
        hybrid_search=True,
        text_search_config="portuguese",
        initialization_fail_on_error=True,
    )


def get_vector_count() -> int:
    """Conta quantos vetores existem na tabela do índice.

    Returns:
        Quantidade de linhas na tabela de vetores, ou 0 quando ela não existe.
    """
    table_name = f"data_{VECTOR_TABLE_NAME}"

    with get_engine().connect() as connection:
        exists = connection.execute(
            text("SELECT to_regclass(:name)"), {"name": f"public.{table_name}"}
        ).scalar()
        if exists is None:
            return 0

        return connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()


def reset_vector_store() -> PGVectorStore:
    """Recria a tabela de vetores do zero (estrutura e dados).

    Returns:
        `PGVectorStore` com a tabela nova e vazia.
    """
    with get_engine().begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS data_{VECTOR_TABLE_NAME}"))

    vector_store = get_vector_store()
    vector_store.clear()
    return vector_store


@lru_cache(maxsize=1)
def build_or_load_index() -> VectorStoreIndex:
    """Carrega índice persistido ou reconstrói quando necessário.

    Returns:
        Índice vetorial pronto para consultas.
    """
    start = time.perf_counter()
    configure_llama_index()
    vector_store = get_vector_store()

    if not should_rebuild_index():
        try:
            index = VectorStoreIndex.from_vector_store(
                vector_store,
                embed_model=create_embed_model(),
            )
            logger.info(
                "Index carregado do PostgreSQL em %.2fs.",
                time.perf_counter() - start,
            )
            return index
        except Exception:
            logger.exception("Falha ao carregar índice do PostgreSQL. Reconstruindo.")

    documents = load_documents()
    vector_store = reset_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
    )
    write_index_metadata(get_index_metadata())
    logger.info(
        "Index reconstruído no PostgreSQL em %.2fs com %s documentos.",
        time.perf_counter() - start,
        len(documents),
    )
    return index


class CatalogAndSalesRetriever(BaseRetriever):
    """Busca catálogo (produtos e vendedores) e vendas em separado.

    As 500 vendas repetem nomes de produtos e vendedores e, numa busca única,
    tomam o lugar dos cadastros. Buscando cada grupo à parte, as perguntas do
    tipo "quais produtos..." sempre recebem os cadastros no contexto.
    """

    def __init__(
        self,
        index: VectorStoreIndex,
        usuario: Usuario,
        top_k: int = 4,
        sales_top_k: int = 2,
    ) -> None:
        super().__init__()
        self._usuario = usuario
        access = build_access_filters(usuario)
        self._catalog = index.as_retriever(
            similarity_top_k=top_k,
            sparse_top_k=top_k,
            vector_store_query_mode="hybrid",
            filters=MetadataFilters(
                filters=[
                    MetadataFilter(
                        key="tipo",
                        value=["produto", "vendedor", "funcionario"],
                        operator=FilterOperator.IN,
                    ),
                    access,
                ],
                condition=FilterCondition.AND,
            ),
        )
        self._sales = index.as_retriever(
            similarity_top_k=sales_top_k,
            sparse_top_k=sales_top_k,
            vector_store_query_mode="hybrid",
            filters=MetadataFilters(
                filters=[MetadataFilter(key="tipo", value="venda"), access],
                condition=FilterCondition.AND,
            ),
        )

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        if FIRST_PERSON.search(query_bundle.query_str):
            # "meu salário", "minhas vendas": a busca precisa do nome de quem pergunta.
            query_bundle = QueryBundle(f"{query_bundle.query_str} ({self._usuario.nome})")

        nodes = self._catalog.retrieve(query_bundle) + self._sales.retrieve(query_bundle)
        # Segunda barreira: o filtro já roda no banco, mas aqui nada proibido passa.
        nodes = filtrar_resultados(self._usuario, nodes)
        unique: dict[str, NodeWithScore] = {}
        for node in nodes:
            unique.setdefault(node.node.node_id, node)
        return list(unique.values())


def create_query_engine(index: VectorStoreIndex, usuario: Usuario):
    """Cria query engine com configuração otimizada para RAG curto.

    Args:
        index: Índice vetorial já carregado.
        usuario: Quem consulta; define o que a busca pode devolver.

    Returns:
        Query engine configurado.
    """
    return RetrieverQueryEngine.from_args(
        CatalogAndSalesRetriever(index, usuario),
        text_qa_template=QA_TEMPLATE.partial_format(
            usuario_nome=usuario.nome, usuario_papel=usuario.papel
        ),
        response_mode="simple_summarize",
    )


QUERY_ENGINE_LOCK = threading.Lock()


@lru_cache(maxsize=64)
def build_query_engine(usuario: Usuario):
    """Monta o query engine de um usuário (cacheado por usuário)."""
    return create_query_engine(build_or_load_index(), usuario)


def get_query_engine(usuario: Usuario):
    """Retorna o query engine do usuário, com as permissões dele.

    O índice vetorial é compartilhado; só o filtro de acesso muda por usuário.
    O lock evita montar o índice duas vezes quando a pré-carga e a primeira
    conversa chegam ao mesmo tempo.

    Args:
        usuario: Quem consulta.

    Returns:
        Query engine pronto para responder perguntas desse usuário.
    """
    with QUERY_ENGINE_LOCK:
        return build_query_engine(usuario)


def warm_up() -> None:
    """Carrega modelo de embeddings e índice antes da primeira conversa."""
    try:
        start = time.perf_counter()
        with QUERY_ENGINE_LOCK:
            build_or_load_index()
        logger.info("Pré-carga concluída em %.2fs.", time.perf_counter() - start)
    except Exception:
        logger.exception("Falha na pré-carga; será tentada de novo na primeira conversa.")


def authenticate(email: str, password: str) -> Usuario | None:
    """Confere e-mail e senha na tabela `usuarios`.

    Args:
        email: E-mail digitado.
        password: Senha digitada.

    Returns:
        O `Usuario` autenticado, ou `None` se a conta não existe, está inativa
        ou a senha não confere.
    """
    with get_engine().connect() as connection:
        row = (
            connection.execute(
                text(
                    "SELECT usuario_id, nome, papel, funcionario_id, cliente_id, senha_hash "
                    "FROM usuarios WHERE lower(email) = :email AND ativo"
                ),
                {"email": email.strip().lower()},
            )
            .mappings()
            .first()
        )

    # Conta inexistente também gasta o tempo de uma verificação, para o tempo de
    # resposta não revelar quais e-mails existem.
    stored_hash = row["senha_hash"] if row else DUMMY_PASSWORD_HASH
    password_ok = verify_password(password, stored_hash)
    if row is None or not password_ok:
        return None

    return Usuario(
        usuario_id=row["usuario_id"],
        nome=row["nome"],
        papel=row["papel"],
        funcionario_id=row["funcionario_id"],
        cliente_id=row["cliente_id"],
    )


@cl.password_auth_callback
async def auth_callback(username: str, password: str) -> cl.User | None:
    """Login do Chainlit: contas fictícias da tabela `usuarios`."""
    usuario = await cl.make_async(authenticate)(username, password)
    if usuario is None:
        logger.warning("Login recusado para %s.", username[:60])
        return None

    return cl.User(identifier=username.strip().lower(), metadata=usuario.to_metadata())


def current_user() -> Usuario:
    """Usuário logado na sessão atual do Chainlit."""
    app_user = cl.user_session.get("user")
    return Usuario.from_metadata(app_user.metadata)


@cl.on_app_startup
async def on_app_startup() -> None:
    """Abre o servidor logo e aquece o RAG em segundo plano."""
    threading.Thread(target=warm_up, daemon=True).start()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa sessão do usuário e prepara engine de consulta."""
    usuario = current_user()
    query_engine = await cl.make_async(get_query_engine)(usuario)

    cl.user_session.set("query_engine", query_engine)

    await cl.Message(
        content=(
            f"Oi, {usuario.nome.split()[0]}! Eu sou a Carol, da AiBites. "
            "Consulto produtos, vendedores e vendas conforme o seu acesso. "
            "Exemplo: `Qual valor do notebook Dell?`"
        )
    ).send()


@cl.on_message
async def main(message: cl.Message) -> None:
    """Processa mensagem do usuário e retorna resposta do RAG.

    Args:
        message: Mensagem recebida pelo Chainlit.
    """
    query_engine = cl.user_session.get("query_engine")

    if query_engine is None:
        query_engine = await cl.make_async(get_query_engine)(current_user())
        cl.user_session.set("query_engine", query_engine)

    start = time.perf_counter()
    response = await cl.make_async(query_engine.query)(message.content)
    logger.info("Consulta concluída em %.2fs.", time.perf_counter() - start)

    await cl.Message(content=str(response)).send()
