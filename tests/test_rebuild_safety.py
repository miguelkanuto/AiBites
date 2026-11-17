"""Recriar o índice não pode deixar o site sem índice quando o provedor de embeddings falha."""

import pytest
from llama_index.core import Document

import main
from embeddings import EmbeddingError


class _Modelo:
    def __init__(self, erro: Exception | None = None):
        self._erro = erro

    def get_text_embedding_batch(self, textos: list[str], **_: object) -> list[list[float]]:
        if self._erro:
            raise self._erro
        return [[0.1, 0.2] for _ in textos]


class _Store:
    def __init__(self):
        self.nos: list = []

    def add(self, nos: list) -> None:
        self.nos.extend(nos)


@pytest.fixture
def ambiente(monkeypatch):
    chamadas: list[str] = []
    store = _Store()
    monkeypatch.setenv("AIBITES_ADMIN_DATABASE_URL", "postgresql://dono:x@localhost/teste")
    monkeypatch.setattr(main, "configure_llama_index", lambda: None)
    monkeypatch.setattr(main, "load_documents", lambda: [Document(text="Impressora HP DeskJet", metadata={"tipo": "produto"})])
    monkeypatch.setattr(main, "reset_vector_store", lambda: chamadas.append("reset") or store)
    monkeypatch.setattr(main, "grant_read_to_app_role", lambda: chamadas.append("grant"))
    monkeypatch.setattr(main, "write_index_metadata", lambda metadata: chamadas.append("manifesto"))
    monkeypatch.setattr(main, "get_index_metadata", lambda: {"data_hash": "x", "embed_model": "m"})
    return chamadas, store


def test_falha_do_provedor_nao_apaga_a_tabela_nem_troca_o_manifesto(monkeypatch, ambiente):
    chamadas, store = ambiente
    monkeypatch.setattr(main, "create_embed_model", lambda: _Modelo(EmbeddingError("sem cota (HTTP 429)")))

    with pytest.raises(EmbeddingError):
        main.rebuild_index()

    assert chamadas == []  # nada de reset, grant ou manifesto
    assert store.nos == []


def test_sucesso_apaga_grava_os_vetores_e_devolve_a_leitura_ao_app(monkeypatch, ambiente):
    chamadas, store = ambiente
    monkeypatch.setattr(main, "create_embed_model", lambda: _Modelo())

    main.rebuild_index()

    assert chamadas == ["reset", "grant", "manifesto"]
    assert len(store.nos) == 1
    assert store.nos[0].embedding == [0.1, 0.2]
