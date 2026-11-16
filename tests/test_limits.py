"""Testes dos limites persistentes: regras puras e contagens no banco."""

import os

import pytest
from limits import (
    LOGIN_GLOBAL_MAX_FAILURES,
    LOGIN_MAX_FAILURES,
    MESSAGES_PER_DAY,
    MESSAGES_PER_MINUTE,
    RISK_PAUSE_THRESHOLD,
    login_blocked,
    rate_decision,
    risk_paused,
)
from sqlalchemy import text

# --- Regras puras (sem banco) ---


def test_login_bloqueia_no_limite_de_falhas_do_email() -> None:
    assert login_blocked(LOGIN_MAX_FAILURES - 1, 0) is False
    assert login_blocked(LOGIN_MAX_FAILURES, 0) is True


def test_login_bloqueia_no_limite_global() -> None:
    assert login_blocked(0, LOGIN_GLOBAL_MAX_FAILURES - 1) is False
    assert login_blocked(0, LOGIN_GLOBAL_MAX_FAILURES) is True


def test_mensagens_dentro_do_limite_passam() -> None:
    decisao = rate_decision(MESSAGES_PER_MINUTE - 1, 0, MESSAGES_PER_DAY - 1)

    assert decisao.allowed is True
    assert decisao.retry_after == 0


def test_limite_por_minuto_informa_quanto_esperar() -> None:
    decisao = rate_decision(MESSAGES_PER_MINUTE, 41.2, 50)

    assert decisao.allowed is False
    assert decisao.reason == "minuto"
    assert decisao.retry_after == 42


def test_limite_por_dia() -> None:
    decisao = rate_decision(1, 0, MESSAGES_PER_DAY)

    assert decisao.allowed is False
    assert decisao.reason == "dia"


def test_risco_pausa_no_limite() -> None:
    assert risk_paused(RISK_PAUSE_THRESHOLD - 1) is False
    assert risk_paused(RISK_PAUSE_THRESHOLD) is True


# --- Contagens no banco (integração) ---

TESTE = "TESTE-LIMITES"


@pytest.fixture
def banco():
    if not os.getenv("AIBITES_DATABASE_URL") or not os.getenv("AIBITES_ADMIN_DATABASE_URL"):
        pytest.skip("Precisa de AIBITES_DATABASE_URL e AIBITES_ADMIN_DATABASE_URL")

    import main

    yield main.get_engine(), main.get_limits()

    with main.get_admin_engine().begin() as connection:
        connection.execute(text("DELETE FROM log_conversas WHERE usuario_id = :u"), {"u": TESTE})
        connection.execute(text("DELETE FROM eventos_seguranca WHERE usuario = :u"), {"u": TESTE})


def _evento(engine, tipo: str, quantidade: int = 1) -> None:
    with engine.begin() as connection:
        for _ in range(quantidade):
            connection.execute(
                text("INSERT INTO eventos_seguranca (tipo, usuario) VALUES (:t, :u)"), {"t": tipo, "u": TESTE}
            )


def _mensagens(engine, quantidade: int, risco: int = 0) -> None:
    with engine.begin() as connection:
        for _ in range(quantidade):
            connection.execute(
                text("INSERT INTO log_conversas (usuario_id, papel, pergunta, risco) VALUES (:u, 'vendedor', 'x', :r)"),
                {"u": TESTE, "r": risco},
            )


@pytest.mark.integration
def test_login_bloqueia_depois_de_falhas_e_libera_apos_login_correto(banco) -> None:
    engine, limits = banco
    _evento(engine, "login_falho", LOGIN_MAX_FAILURES - 1)
    assert limits.login_blocked(TESTE) is False

    _evento(engine, "login_falho")
    assert limits.login_blocked(TESTE) is True

    _evento(engine, "login_ok")
    assert limits.login_blocked(TESTE) is False


@pytest.mark.integration
def test_bloqueio_de_login_nao_atinge_outro_email(banco) -> None:
    engine, limits = banco
    _evento(engine, "login_falho", LOGIN_MAX_FAILURES)

    assert limits.login_blocked(TESTE) is True
    assert limits.login_blocked("outra.pessoa@exemplo.com") is False


@pytest.mark.integration
def test_limite_de_mensagens_por_minuto(banco) -> None:
    engine, limits = banco
    _mensagens(engine, MESSAGES_PER_MINUTE - 1)
    assert limits.message_decision(TESTE).allowed is True

    _mensagens(engine, 1)
    decisao = limits.message_decision(TESTE)

    assert decisao.allowed is False
    assert 1 <= decisao.retry_after <= 61


@pytest.mark.integration
def test_limite_de_mensagens_nao_afeta_outro_usuario(banco) -> None:
    engine, limits = banco
    _mensagens(engine, MESSAGES_PER_MINUTE)

    assert limits.message_decision(TESTE).allowed is False
    assert limits.message_decision("TESTE-OUTRO").allowed is True


@pytest.mark.integration
def test_risco_soma_so_mensagens_suspeitas(banco) -> None:
    engine, limits = banco
    _mensagens(engine, 5, risco=10)  # abaixo do mínimo: não conta
    assert limits.risk_score(TESTE) == 0

    _mensagens(engine, 2, risco=70)
    score = limits.risk_score(TESTE)

    assert score == 140
    assert risk_paused(score) is True
