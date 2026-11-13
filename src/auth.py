"""Senhas e verificação de login dos usuários de demonstração.

As contas são fictícias e ficam na tabela `usuarios`. A senha é guardada com
scrypt (biblioteca padrão), nunca em texto puro.
"""

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    """Gera o hash de uma senha no formato `scrypt$<sal em hex>$<hash em hex>`."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Confere a senha contra o hash guardado, sem vazar tempo de comparação.

    Args:
        password: Senha digitada.
        stored_hash: Valor da coluna `senha_hash`.

    Returns:
        `True` se a senha confere; `False` também para hash malformado.
    """
    try:
        scheme, salt_hex, digest_hex = stored_hash.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
    except ValueError:
        return False

    return hmac.compare_digest(digest, expected)
