"""O usuário do app (menor privilégio) lê o negócio, só insere nos logs e não altera nada."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

TESTE = "TESTE-PRIV"


@pytest.fixture(scope="module")
def engines():
    if not os.getenv("AIBITES_DATABASE_URL") or not os.getenv("AIBITES_ADMIN_DATABASE_URL"):
        pytest.skip("Precisa de AIBITES_DATABASE_URL e AIBITES_ADMIN_DATABASE_URL")

    import main

    app = main.get_engine()
    admin = main.get_admin_engine()

    with app.connect() as connection:
        usuario = connection.execute(text("SELECT current_user")).scalar_one()
    if usuario == "neondb_owner" or usuario == admin.url.username:
        pytest.skip("O app está conectado como dono do banco; rode db/setup_roles.py")

    yield app, admin

    with admin.begin() as connection:
        connection.execute(text("DELETE FROM log_conversas WHERE usuario_id = :u"), {"u": TESTE})


def test_app_le_as_tabelas_de_negocio(engines) -> None:
    app, _ = engines
    with app.connect() as connection:
        for tabela in ("produtos", "vendedores", "vendas", "funcionarios", "clientes", "usuarios"):
            assert connection.execute(text(f"SELECT count(*) FROM {tabela}")).scalar_one() > 0


@pytest.mark.parametrize(
    "comando",
    [
        "INSERT INTO produtos (produto_id, nome, categoria, marca, descricao, preco_unitario) "
        "VALUES ('PX', 'x', 'x', 'x', 'x', 1)",
        "UPDATE funcionarios SET salario = 1",
        "UPDATE usuarios SET papel = 'ceo'",
        "DELETE FROM vendas",
        "DROP TABLE produtos",
        "TRUNCATE vendas",
        "CREATE TABLE intruso (id int)",
        "DELETE FROM log_conversas",
        "UPDATE log_conversas SET pergunta = 'apagado'",
    ],
)
def test_app_nao_altera_dados_nem_estrutura(engines, comando: str) -> None:
    app, _ = engines
    with pytest.raises(DBAPIError):
        with app.begin() as connection:
            connection.execute(text(comando))


def test_app_insere_nos_logs(engines) -> None:
    app, admin = engines
    with app.begin() as connection:
        connection.execute(
            text("INSERT INTO log_conversas (usuario_id, papel, pergunta) VALUES (:u, 'vendedor', 'oi')"),
            {"u": TESTE},
        )
        connection.execute(
            text("INSERT INTO eventos_seguranca (tipo, usuario) VALUES ('teste_privilegio', :u)"), {"u": TESTE}
        )

    with admin.begin() as connection:
        connection.execute(text("DELETE FROM eventos_seguranca WHERE usuario = :u"), {"u": TESTE})


def test_app_le_a_tabela_de_vetores(engines) -> None:
    app, _ = engines
    with app.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM data_sales_rag")).scalar_one() > 0
