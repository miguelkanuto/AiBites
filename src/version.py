"""Versão do produto (SemVer: MAIOR.MENOR.CORREÇÃO). Única fonte no código; o teste `test_version` mantém
`pyproject.toml` e `web/package.json` iguais a ela. Mudou o site ou a API: suba a versão e anote no CHANGELOG.md.
"""

import os

VERSION = "1.0.1"


def build_id() -> str:
    """Identifica o deploy (commit no Render). Muda a cada publicação, mesmo sem subir a versão."""
    return (os.getenv("RENDER_GIT_COMMIT") or os.getenv("AIBITES_BUILD") or "local")[:7]
