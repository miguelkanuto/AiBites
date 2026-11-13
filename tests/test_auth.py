"""Testes unitários do hash de senhas."""

from auth import hash_password, verify_password


def test_senha_correta_confere() -> None:
    assert verify_password("demo123", hash_password("demo123")) is True


def test_senha_errada_nao_confere() -> None:
    assert verify_password("outra", hash_password("demo123")) is False


def test_mesmo_texto_gera_hashes_diferentes() -> None:
    assert hash_password("demo123") != hash_password("demo123")


def test_hash_nao_contem_a_senha() -> None:
    assert "demo123" not in hash_password("demo123")


def test_hash_malformado_nao_autentica() -> None:
    for invalido in ("", "texto-solto", "md5$aa$bb", "scrypt$zz$zz", "scrypt$aa"):
        assert verify_password("demo123", invalido) is False
