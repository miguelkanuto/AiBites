"""Modo do servidor público: sem a credencial de dono do banco, o índice só é lido.

Sem isso, o contêiner (que não tem `storage/index_metadata.json`) tentaria refazer
o índice na partida e falharia por falta de permissão.
"""

import pytest

import main


@pytest.fixture
def com_indice(monkeypatch):
    monkeypatch.setattr(main, "get_vector_count", lambda: 500)


def test_servidor_publico_usa_indice_existente_sem_manifesto_local(monkeypatch, com_indice):
    monkeypatch.delenv("AIBITES_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "read_index_metadata", lambda: None)

    def nao_deve_calcular():
        raise AssertionError("não deve ler todas as tabelas para comparar o índice")

    monkeypatch.setattr(main, "get_index_metadata", nao_deve_calcular)
    assert main.should_rebuild_index() is False


def test_servidor_publico_com_indice_vazio_pede_reconstrucao(monkeypatch):
    monkeypatch.delenv("AIBITES_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "get_vector_count", lambda: 0)
    assert main.should_rebuild_index() is True


def test_com_dono_do_banco_manifesto_diferente_reconstroi(monkeypatch, com_indice):
    monkeypatch.setenv("AIBITES_ADMIN_DATABASE_URL", "postgresql://dono:x@localhost/teste")
    monkeypatch.setattr(main, "read_index_metadata", lambda: {"data_hash": "a", "embed_model": "m"})
    monkeypatch.setattr(main, "get_index_metadata", lambda: {"data_hash": "b", "embed_model": "m"})
    assert main.should_rebuild_index() is True


def test_com_dono_do_banco_manifesto_igual_nao_reconstroi(monkeypatch, com_indice):
    monkeypatch.setenv("AIBITES_ADMIN_DATABASE_URL", "postgresql://dono:x@localhost/teste")
    igual = {"data_hash": "a", "embed_model": "m"}
    monkeypatch.setattr(main, "read_index_metadata", lambda: igual)
    monkeypatch.setattr(main, "get_index_metadata", lambda: dict(igual))
    assert main.should_rebuild_index() is False
