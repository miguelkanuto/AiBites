"""Testes de integração do log de auditoria (PostgreSQL de teste, sem LLM)."""

import os

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

TESTE = "TESTE-PYTEST"


@pytest.fixture
def engine():
    if not os.getenv("AIBITES_DATABASE_URL"):
        pytest.skip("AIBITES_DATABASE_URL não configurada")

    import main

    engine = main.get_engine()
    yield engine
    # O usuário do app só insere nos logs; a limpeza do teste usa o dono do banco.
    with main.get_admin_engine().begin() as connection:
        connection.execute(text("DELETE FROM log_conversas WHERE usuario_id = :u"), {"u": TESTE})
        connection.execute(text("DELETE FROM eventos_seguranca WHERE usuario = :u"), {"u": TESTE})


def test_log_grava_pergunta_sem_dados_pessoais(engine) -> None:
    from audit import log_conversation

    log_conversation(
        engine,
        usuario_id=TESTE,
        papel="vendedor",
        pergunta="Meu CPF é 529.982.247-25 e meu e-mail é ana@loja.com",
        resposta="Anotado, ligue (11) 91234-5678",
        motivos=("teste",),
        risco=10,
        documentos=("produto:P001",),
        latencia_ms=123,
    )

    with engine.connect() as connection:
        linha = connection.execute(
            text("SELECT pergunta, resposta, motivos, documentos, bloqueada FROM log_conversas WHERE usuario_id = :u"),
            {"u": TESTE},
        ).one()

    assert "529.982.247-25" not in linha.pergunta
    assert "ana@loja.com" not in linha.pergunta
    assert "[CPF]" in linha.pergunta and "[EMAIL]" in linha.pergunta
    assert "[TELEFONE]" in linha.resposta
    assert linha.motivos == ["teste"]
    assert linha.documentos == ["produto:P001"]
    assert linha.bloqueada is False


def test_evento_de_seguranca_e_gravado(engine) -> None:
    from audit import log_event

    log_event(engine, "login_falho", TESTE, "senha errada")

    with engine.connect() as connection:
        tipo = connection.execute(
            text("SELECT tipo FROM eventos_seguranca WHERE usuario = :u"), {"u": TESTE}
        ).scalar_one()

    assert tipo == "login_falho"


def test_falha_ao_gravar_nao_derruba_o_chat() -> None:
    from audit import log_conversation
    from sqlalchemy import create_engine

    engine_quebrado = create_engine("postgresql+psycopg2://x:y@127.0.0.1:1/nada", connect_args={"connect_timeout": 1})

    log_conversation(engine_quebrado, usuario_id=TESTE, papel="vendedor", pergunta="oi")  # não levanta
