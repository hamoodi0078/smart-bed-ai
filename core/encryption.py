"""Field-level encryption for sensitive database columns.

Usage
-----
Use ``EncryptedText`` as a SQLAlchemy column type to transparently encrypt
and decrypt any string field:

    from core.encryption import EncryptedText

    class SleepSession(Base):
        heart_rate_data: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

Configuration
-------------
Set ``DATA_ENCRYPTION_KEY`` in your environment / .env to a URL-safe base64
Fernet key.  Generate one with::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If the key is not set the module falls back to a **deterministic dev-only key**
and logs a loud warning.  In production the app will refuse to start without
a proper key (enforced by ``config/settings.py``).
"""

from __future__ import annotations

import base64
import logging
import os

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

_DEV_FALLBACK_KEY = b"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def _load_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package is required for field-level encryption. "
            "Run: pip install cryptography"
        ) from exc

    raw = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    if not raw:
        is_production = os.getenv("DANAH_ENV", "development").lower() == "production"
        if is_production:
            raise RuntimeError(
                "DATA_ENCRYPTION_KEY is not set. "
                "Generate one: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        logger.warning(
            "DATA_ENCRYPTION_KEY not set — using insecure dev-only fallback key. "
            "Set DATA_ENCRYPTION_KEY in .env before any real data is stored."
        )
        key = _DEV_FALLBACK_KEY
    else:
        key = raw.encode()

    return Fernet(key)


_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = _load_fernet()
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 ciphertext string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt *ciphertext* returned by :func:`encrypt_value`."""
    from cryptography.fernet import InvalidToken
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Decryption failed — ciphertext is corrupt, truncated, or was encrypted "
            "with a different key."
        ) from exc


class EncryptedText(TypeDecorator):
    """SQLAlchemy column type that transparently encrypts/decrypts string values.

    Store on disk: encrypted Fernet token (URL-safe base64, ~120+ bytes per value).
    Retrieved in Python: original plaintext string.

    Example::

        class User(Base):
            full_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_value(str(value))

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        try:
            return decrypt_value(value)
        except ValueError:
            logger.error(
                "Failed to decrypt a database field — returning None. "
                "Check DATA_ENCRYPTION_KEY matches the key used to write this row."
            )
            return None
