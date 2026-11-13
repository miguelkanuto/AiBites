import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

from rbac import Usuario  # noqa: E402

# Usuários fictícios iguais aos do db/seed.py.
VENDEDOR_CARLOS = Usuario("U001", "Carlos Lima", "vendedor", funcionario_id="F002")
VENDEDOR_RAFAEL = Usuario("U002", "Rafael Martins", "vendedor", funcionario_id="F006")
GERENTE_MARCOS = Usuario("U003", "Marcos Teixeira", "gerente_vendas", funcionario_id="F011")
RH_JULIANA = Usuario("U004", "Juliana Prado", "rh", funcionario_id="F012")
TI_RODRIGO = Usuario("U005", "Rodrigo Campos", "ti", funcionario_id="F013")
CEO_HELENA = Usuario("U006", "Helena Vasconcelos", "ceo", funcionario_id="F014")
CLIENTE_PAULO = Usuario("U007", "Paulo Mendes", "cliente", cliente_id="C001")

CEO_FUNCIONARIO_ID = "F014"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: precisa do PostgreSQL de teste e do modelo de embeddings"
    )
