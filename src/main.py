import csv
import hashlib
import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import chainlit as cl
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv
from llama_index.core import (
    PromptTemplate,
    Settings,
    Document,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openrouter import OpenRouter
from llama_index.vector_stores.chroma import ChromaVectorStore

_ = load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "sales.csv"
STORAGE_DIR = BASE_DIR / "storage"
INDEX_METADATA_PATH = STORAGE_DIR / "index_metadata.json"
CHROMA_DIR = STORAGE_DIR / "chroma"
CHROMA_COLLECTION_NAME = "sales"


QA_TEMPLATE = PromptTemplate(
    """
Você é um assistente especializado em consultar uma base de vendas.

Regras:
- Responda sempre em português do Brasil.
- Use apenas informações do contexto.
- Se a pergunta for sobre preço/valor de produto, responda com o preço unitário quando existir.
- Se houver mais de uma venda do mesmo produto, explique que o produto aparece em mais de uma venda.
- Se a pergunta envolver quantidade ou total vendido, use os campos quantidade e valor_total.
- Se a informação não estiver no contexto, diga que não encontrou a informação na base.

Contexto:
{context_str}

Pergunta:
{query_str}

Resposta final:
    """
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
def create_embed_model() -> HuggingFaceEmbedding:
    """Cria modelo de embeddings reutilizável.

    Returns:
        Instância de `HuggingFaceEmbedding`.
    """
    return HuggingFaceEmbedding(model_name=os.environ["EMBED_MODEL"])


def configure_llama_index() -> None:
    """Configura componentes globais usados pelo LlamaIndex."""
    Settings.llm = create_llm()
    Settings.embed_model = create_embed_model()
    Settings.chunk_size = 512
    Settings.chunk_overlap = 50


def load_sales_documents(csv_path: Path) -> list[Document]:
    """Converte CSV de vendas em documentos indexáveis.

    Cada linha vira um documento independente com rótulos de coluna,
    o que melhora recuperação semântica e reduz contexto irrelevante.

    Args:
        csv_path: Caminho do arquivo CSV de vendas.

    Returns:
        Lista de documentos prontos para indexação.
    """
    documents: list[Document] = []

    with csv_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            lines = [f"{key}: {value}" for key, value in row.items()]
            documents.append(
                Document(
                    text="\n".join(lines),
                    metadata={
                        "file_name": csv_path.name,
                        "file_path": str(csv_path),
                        "venda_id": row.get("venda_id", ""),
                        "produto_id": row.get("produto_id", ""),
                        "produto_nome": row.get("produto_nome", ""),
                    },
                )
            )

    return documents


def calculate_file_hash(file_path: Path) -> str:
    """Calcula hash SHA-256 de arquivo.

    Args:
        file_path: Caminho do arquivo alvo.

    Returns:
        Hash hexadecimal do conteúdo.
    """
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)

    return digest.hexdigest()


def get_index_metadata() -> dict[str, Any]:
    """Gera metadados usados para validar o índice persistido.

    Returns:
        Caminho e hash do CSV e modelo de embeddings atuais.
    """
    return {
        "csv_path": str(CSV_PATH),
        "csv_hash": calculate_file_hash(CSV_PATH),
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
        `True` quando storage está ausente ou CSV/modelo mudou.
    """
    if not STORAGE_DIR.exists() or get_chroma_collection().count() == 0:
        return True

    persisted_metadata = read_index_metadata()
    current_metadata = get_index_metadata()
    return persisted_metadata != current_metadata


@lru_cache(maxsize=1)
def get_chroma_client() -> ClientAPI:
    """Cria cliente ChromaDB embarcado, persistido em disco.

    Returns:
        Cliente `PersistentClient` (sem servidor, roda dentro do app).
    """
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_chroma_collection() -> Collection:
    """Retorna coleção Chroma de vendas, criando quando não existe.

    Returns:
        Coleção `sales` do ChromaDB.
    """
    return get_chroma_client().get_or_create_collection(CHROMA_COLLECTION_NAME)


def get_vector_store() -> ChromaVectorStore:
    """Cria vector store apontando para a coleção atual do ChromaDB.

    Returns:
        `ChromaVectorStore` da coleção de vendas.
    """
    return ChromaVectorStore(chroma_collection=get_chroma_collection())


def reset_chroma_collection() -> ChromaVectorStore:
    """Remove coleção antiga e recria coleção limpa no ChromaDB.

    Returns:
        `ChromaVectorStore` apontando para coleção recriada.
    """
    client = get_chroma_client()

    try:
        client.delete_collection(CHROMA_COLLECTION_NAME)
    except Exception:
        logger.debug("Coleção Chroma ainda não existia.")

    chroma_collection = client.get_or_create_collection(CHROMA_COLLECTION_NAME)
    return ChromaVectorStore(chroma_collection=chroma_collection)


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
                "Index carregado do ChromaDB em %.2fs.",
                time.perf_counter() - start,
            )
            return index
        except Exception:
            logger.exception("Falha ao carregar índice do ChromaDB. Reconstruindo.")

    documents = load_sales_documents(CSV_PATH)
    vector_store = reset_chroma_collection()
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
    )
    write_index_metadata(get_index_metadata())
    logger.info(
        "Index reconstruído no ChromaDB em %.2fs com %s documentos.",
        time.perf_counter() - start,
        len(documents),
    )
    return index


def create_query_engine(index: VectorStoreIndex):
    """Cria query engine com configuração otimizada para RAG curto.

    Args:
        index: Índice vetorial já carregado.

    Returns:
        Query engine configurado.
    """
    return index.as_query_engine(
        similarity_top_k=4,
        text_qa_template=QA_TEMPLATE,
        response_mode="simple_summarize",
    )


@lru_cache(maxsize=1)
def get_query_engine():
    """Retorna query engine compartilhado entre sessões.

    Returns:
        Query engine pronto para responder perguntas.
    """
    return create_query_engine(build_or_load_index())


@cl.on_chat_start
async def on_chat_start() -> None:
    """Inicializa sessão do usuário e prepara engine de consulta."""
    query_engine = await cl.make_async(get_query_engine)()

    cl.user_session.set("query_engine", query_engine)

    await cl.Message(
        content=(
            "RAG iniciado com o CSV de vendas. Exemplo: `Qual valor do notebook Dell?`"
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
        query_engine = await cl.make_async(get_query_engine)()
        cl.user_session.set("query_engine", query_engine)

    start = time.perf_counter()
    response = await cl.make_async(query_engine.query)(message.content)
    logger.info("Consulta concluída em %.2fs.", time.perf_counter() - start)

    await cl.Message(content=str(response)).send()
