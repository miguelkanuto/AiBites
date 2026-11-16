"""Cria o usuário `aibites_app` (menor privilégio) e ajusta o `.env`.

O app passa a conectar com esse usuário: ele lê as tabelas de negócio e só
escreve nos logs. O usuário dono do banco fica em `AIBITES_ADMIN_DATABASE_URL`,
usado apenas para recriar o índice vetorial e rodar o seed.

Uso (na raiz do projeto):
    uv run python db/setup_roles.py            # cria o usuário se não existir
    uv run python db/setup_roles.py --rotate   # gera uma senha nova

A senha é gerada aqui e gravada só no `.env`; ela não é impressa.
"""

import os
import re
import secrets
import sys
from pathlib import Path

import psycopg2
from dotenv import dotenv_values, load_dotenv
from psycopg2 import sql
from sqlalchemy.engine import make_url

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
ROLE = os.getenv("AIBITES_APP_ROLE", "aibites_app")

READ_TABLES = ["produtos", "vendedores", "vendas", "funcionarios", "clientes", "usuarios"]
WRITE_TABLES = ["log_conversas", "eventos_seguranca", "tool_calls"]  # só leitura e inserção (logs não são editados)


def set_env_value(content: str, key: str, value: str) -> str:
    """Troca (ou acrescenta) `CHAVE=valor` no texto de um .env, sem tocar nas outras linhas."""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(content):
        return pattern.sub(lambda _: line, content)
    return content.rstrip("\n") + "\n" + line + "\n"


def main() -> None:
    rotate = "--rotate" in sys.argv
    _ = load_dotenv(ENV_PATH)
    values = dotenv_values(ENV_PATH)

    admin_url = values.get("AIBITES_ADMIN_DATABASE_URL") or values.get("AIBITES_DATABASE_URL")
    if not admin_url:
        raise SystemExit("Defina AIBITES_DATABASE_URL (dono do banco) no .env antes de rodar.")

    admin = make_url(admin_url)
    if admin.username == ROLE:
        raise SystemExit(
            "A URL atual já é a do usuário do app. Defina AIBITES_ADMIN_DATABASE_URL com a do dono do banco."
        )

    password = secrets.token_urlsafe(24)
    created = False

    with psycopg2.connect(admin_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
        exists = cursor.fetchone() is not None

        if not exists:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(ROLE), sql.Literal(password))
            )
            created = True
        elif rotate:
            cursor.execute(
                sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(sql.Identifier(ROLE), sql.Literal(password))
            )
            created = True

        role = sql.Identifier(ROLE)
        cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(admin.database), role))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))

        for table in READ_TABLES:
            cursor.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(table), role))
        for table in WRITE_TABLES:
            cursor.execute(sql.SQL("GRANT SELECT, INSERT ON {} TO {}").format(sql.Identifier(table), role))
        # O cache também atualiza o contador de acertos.
        cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON cache_semantico TO {}").format(role))
        cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))

        cursor.execute("SELECT to_regclass('public.data_sales_rag')")
        if cursor.fetchone()[0] is not None:
            cursor.execute(sql.SQL("GRANT SELECT ON data_sales_rag TO {}").format(role))

    content = ENV_PATH.read_text(encoding="utf-8")
    content = set_env_value(content, "AIBITES_ADMIN_DATABASE_URL", admin.render_as_string(hide_password=False))
    if created:
        app_url = admin.set(username=ROLE, password=password)
        content = set_env_value(content, "AIBITES_DATABASE_URL", app_url.render_as_string(hide_password=False))
    ENV_PATH.write_text(content, encoding="utf-8")

    if created:
        print(f"Usuário '{ROLE}' pronto; AIBITES_DATABASE_URL (app) e AIBITES_ADMIN_DATABASE_URL (dono) gravadas no .env.")
    else:
        print(f"Usuário '{ROLE}' já existia: permissões reaplicadas; o .env não foi alterado (use --rotate para trocar a senha).")


if __name__ == "__main__":
    main()
