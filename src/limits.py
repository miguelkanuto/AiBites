"""Limites de uso persistentes: login, mensagens e pontuação de risco.

Os contadores saem das próprias tabelas de auditoria (`eventos_seguranca` e
`log_conversas`), então sobrevivem a reinícios e valem para várias instâncias do
app sem precisar de Redis. As regras de decisão são funções puras, fáceis de testar.

Se o banco falhar ao consultar um limite, o app segue (e avisa no log): o banco
fora do ar derruba o resto do app de qualquer jeito.
"""

import logging
from dataclasses import dataclass

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

LOGIN_MAX_FAILURES = 5  # falhas por e-mail na janela
LOGIN_GLOBAL_MAX_FAILURES = 40  # falhas somadas de todos os e-mails na janela
LOGIN_WINDOW_SECONDS = 300

MESSAGES_PER_MINUTE = 10
MESSAGES_PER_DAY = 300

RISK_MIN_POINTS = 30  # só mensagens suspeitas entram na soma
RISK_PAUSE_THRESHOLD = 120
RISK_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class RateDecision:
    """Resultado do limite de mensagens.

    Attributes:
        allowed: `True` se a mensagem pode seguir.
        retry_after: Segundos até poder tentar de novo (0 se liberada).
        reason: `minuto`, `dia` ou vazio.
    """

    allowed: bool
    retry_after: int = 0
    reason: str = ""


def login_blocked(failures: int, global_failures: int) -> bool:
    """Decide o bloqueio de login pelas contagens da janela."""
    return failures >= LOGIN_MAX_FAILURES or global_failures >= LOGIN_GLOBAL_MAX_FAILURES


def rate_decision(last_minute: int, wait_minute: float, last_day: int) -> RateDecision:
    """Decide o limite de mensagens pelas contagens do último minuto e do último dia."""
    if last_minute >= MESSAGES_PER_MINUTE:
        return RateDecision(False, max(1, int(wait_minute) + 1), "minuto")
    if last_day >= MESSAGES_PER_DAY:
        return RateDecision(False, 3600, "dia")
    return RateDecision(True)


def risk_paused(score: int) -> bool:
    """`True` enquanto a pontuação de risco da última hora passa do limite."""
    return score >= RISK_PAUSE_THRESHOLD


class Limits:
    """Consulta as tabelas de auditoria para aplicar os limites."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def login_blocked(self, email: str) -> bool:
        """Falhas de login do e-mail (desde o último login correto) ou do sistema todo."""
        try:
            with self._engine.connect() as connection:
                failures = connection.execute(
                    text(
                        "SELECT count(*) FROM eventos_seguranca "
                        "WHERE tipo = 'login_falho' AND usuario = :email "
                        "AND criado_em > now() - make_interval(secs => :window) "
                        "AND criado_em > COALESCE((SELECT max(criado_em) FROM eventos_seguranca "
                        "WHERE tipo = 'login_ok' AND usuario = :email), 'epoch'::timestamptz)"
                    ),
                    {"email": email, "window": LOGIN_WINDOW_SECONDS},
                ).scalar_one()
                global_failures = connection.execute(
                    text(
                        "SELECT count(*) FROM eventos_seguranca WHERE tipo = 'login_falho' "
                        "AND criado_em > now() - make_interval(secs => :window)"
                    ),
                    {"window": LOGIN_WINDOW_SECONDS},
                ).scalar_one()
            return login_blocked(failures, global_failures)
        except Exception:
            logger.exception("Não foi possível consultar o limite de login.")
            return False

    def message_decision(self, usuario_id: str) -> RateDecision:
        """Limite de mensagens por minuto e por dia (mensagens bloqueadas também contam)."""
        try:
            with self._engine.connect() as connection:
                minute = connection.execute(
                    text(
                        "SELECT count(*) AS n, COALESCE(EXTRACT(EPOCH FROM (min(criado_em) "
                        "+ make_interval(secs => 60) - now())), 0) AS wait "
                        "FROM log_conversas WHERE usuario_id = :u "
                        "AND criado_em > now() - make_interval(secs => 60)"
                    ),
                    {"u": usuario_id},
                ).one()
                day = connection.execute(
                    text(
                        "SELECT count(*) FROM log_conversas WHERE usuario_id = :u "
                        "AND criado_em > now() - make_interval(secs => 86400)"
                    ),
                    {"u": usuario_id},
                ).scalar_one()
            return rate_decision(minute.n, float(minute.wait), day)
        except Exception:
            logger.exception("Não foi possível consultar o limite de mensagens.")
            return RateDecision(True)

    def risk_score(self, usuario_id: str) -> int:
        """Soma dos pontos de risco do usuário na última hora."""
        try:
            with self._engine.connect() as connection:
                return int(
                    connection.execute(
                        text(
                            "SELECT COALESCE(sum(risco), 0) FROM log_conversas "
                            "WHERE usuario_id = :u AND risco >= :minimo "
                            "AND criado_em > now() - make_interval(secs => :window)"
                        ),
                        {"u": usuario_id, "minimo": RISK_MIN_POINTS, "window": RISK_WINDOW_SECONDS},
                    ).scalar_one()
                )
        except Exception:
            logger.exception("Não foi possível consultar a pontuação de risco.")
            return 0
