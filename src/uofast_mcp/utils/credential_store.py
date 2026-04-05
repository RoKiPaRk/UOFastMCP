"""
Credential Store
================

Fernet symmetric encryption for passwords stored in unidata_config.ini.

Key derivation: PBKDF2HMAC(SHA-256, 100k iterations) from JWT_SECRET_KEY + salt.
Cipher: Fernet (AES-128-CBC + HMAC-SHA256) — part of the `cryptography` package,
which is already installed as a transitive dependency of python-jose[cryptography].

Storage format: "ENC:<fernet_token>" — the ENC: prefix distinguishes encrypted
values from plaintext, providing transparent backward compatibility.

Salt: 16 random bytes, hex-encoded and stored in the [encryption] section of
unidata_config.ini. The salt is NOT a secret — it prevents pre-computation
attacks and ties the derived key to this specific installation.

Usage:
    from pathlib import Path
    from .credential_store import encrypt_password, decrypt_password, get_or_create_salt

    config_path = Path("unidata_config.ini")
    jwt_secret  = os.environ["JWT_SECRET_KEY"]

    salt = get_or_create_salt(config_path)
    enc  = encrypt_password("mypassword", jwt_secret, salt)   # "ENC:gAAAAA..."
    dec  = decrypt_password(enc, jwt_secret, salt)             # "mypassword"
"""
from __future__ import annotations

import base64
import configparser
import logging
import os
from pathlib import Path

logger = logging.getLogger("uofast-mcp.credential_store")

_ENC_PREFIX = "ENC:"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_fernet_key(jwt_secret: str, salt: bytes) -> bytes:
    """
    Derive a URL-safe base64-encoded 32-byte key from *jwt_secret* + *salt*
    using PBKDF2-HMAC-SHA256 (100 000 iterations).

    Returns bytes suitable as the key argument to ``Fernet(key)``.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    raw_key = kdf.derive(jwt_secret.encode("utf-8"))
    return base64.urlsafe_b64encode(raw_key)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_encrypted(value: str) -> bool:
    """Return True if *value* was produced by :func:`encrypt_password`."""
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt_password(plaintext: str, jwt_secret: str, salt: bytes) -> str:
    """
    Encrypt *plaintext* using Fernet and the derived key.

    Returns a string of the form ``"ENC:<fernet_token>"``.

    If *jwt_secret* is empty the function logs a warning and returns the
    plaintext unchanged so that the server can still start (with reduced
    security).  This matches the behaviour of the existing codebase, which
    already allows ``JWT_SECRET_KEY`` to be absent at dev time.
    """
    if not jwt_secret:
        logger.warning(
            "JWT_SECRET_KEY is not set — UniData password stored as plaintext. "
            "Set JWT_SECRET_KEY and re-run the setup wizard to encrypt credentials."
        )
        return plaintext

    from cryptography.fernet import Fernet

    fernet_key = _derive_fernet_key(jwt_secret, salt)
    token = Fernet(fernet_key).encrypt(plaintext.encode("utf-8"))
    return _ENC_PREFIX + token.decode("ascii")


def decrypt_password(ciphertext: str, jwt_secret: str, salt: bytes) -> str:
    """
    Decrypt an ``"ENC:..."`` value produced by :func:`encrypt_password`.

    If *ciphertext* does not start with ``"ENC:"`` it is returned unchanged
    (backward compatibility with existing plaintext configs).

    Raises :exc:`ValueError` with a human-readable message if decryption
    fails (wrong key, truncated token, etc.).
    """
    if not is_encrypted(ciphertext):
        return ciphertext

    if not jwt_secret:
        raise ValueError(
            "JWT_SECRET_KEY is required to decrypt stored credentials. "
            "Set the JWT_SECRET_KEY environment variable and restart the server."
        )

    from cryptography.fernet import Fernet, InvalidToken

    raw_token = ciphertext[len(_ENC_PREFIX):].encode("ascii")
    fernet_key = _derive_fernet_key(jwt_secret, salt)
    try:
        return Fernet(fernet_key).decrypt(raw_token).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Failed to decrypt UniData password — JWT_SECRET_KEY may have changed "
            "since unidata_config.ini was written. "
            "Re-run the setup wizard to re-encrypt credentials with the current key."
        ) from exc


def get_or_create_salt(config_path: Path) -> bytes:
    """
    Return the encryption salt for *config_path*.

    Reads the hex-encoded salt from the ``[encryption]`` section of the INI
    file.  If no salt exists yet, generates 16 random bytes, writes them to
    the file atomically, and returns the new salt.

    This function is intentionally **synchronous** — it is called from both
    sync helpers (``_write_unidata_config``) and async startup paths (via
    ``run_in_executor`` or directly, as file I/O here is minimal).
    """
    config = configparser.ConfigParser()

    if config_path.exists():
        config.read(config_path)

    if config.has_section("encryption") and config.has_option("encryption", "salt"):
        try:
            return bytes.fromhex(config.get("encryption", "salt"))
        except ValueError:
            logger.warning(
                "Malformed encryption salt in %s — generating a new one.", config_path
            )

    # Generate a fresh salt and write it back to the file.
    new_salt = os.urandom(16)
    if not config.has_section("encryption"):
        config.add_section("encryption")
    config.set("encryption", "salt", new_salt.hex())

    _write_config_atomic(config_path, config)
    logger.info("Generated new encryption salt and stored in %s", config_path)
    return new_salt


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_config_atomic(path: Path, config: configparser.ConfigParser) -> None:
    """Write *config* to *path* atomically via a temp file + os.replace."""
    tmp = path.with_suffix(".ini.tmp")
    try:
        with tmp.open("w") as fh:
            fh.write(
                "; UOFast MCP Server — Connection Configuration\n"
                "; Passwords are Fernet-encrypted (AES-128-CBC).\n"
                "; Do not edit the password fields manually.\n\n"
            )
            config.write(fh)
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
