"""A versão tem uma fonte só (src/version.py); pyproject, package.json e CHANGELOG precisam acompanhá-la."""

import json
import re
import tomllib
from pathlib import Path

from version import VERSION, build_id

RAIZ = Path(__file__).resolve().parent.parent


def test_versao_segue_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", VERSION)


def test_pyproject_package_json_e_changelog_concordam():
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((RAIZ / "web" / "package.json").read_text(encoding="utf-8"))
    changelog = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    assert pyproject["project"]["version"] == VERSION
    assert package["version"] == VERSION
    assert f"## {VERSION}" in changelog


def test_build_vem_do_ambiente(monkeypatch):
    monkeypatch.delenv("AIBITES_BUILD", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567")
    assert build_id() == "abcdef1"
    monkeypatch.delenv("RENDER_GIT_COMMIT")
    assert build_id() == "local"
