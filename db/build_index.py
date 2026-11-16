"""Recria o índice vetorial no PostgreSQL (exige AIBITES_ADMIN_DATABASE_URL).

Use depois de mudar os dados, as regras de acesso ou o modelo de embeddings,
principalmente em produção, onde o app não tem permissão para recriar o índice.

Uso (na raiz do projeto):
    uv run python db/build_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import main  # noqa: E402

if __name__ == "__main__":
    main.rebuild_index()
    print(f"Índice recriado: {main.get_vector_count()} documentos.")
