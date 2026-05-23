"""Input sanitization and masking helpers."""

from __future__ import annotations

import re


def sanitize_string(
    value: str,
    *,
    max_length: int = 256,
    strip_control_chars: bool = True,
) -> str:
    """Strip, truncate, and optionally remove non-printable control characters."""
    text = str(value or "").strip()
    if strip_control_chars:
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_length]


def mask_email(email: str) -> str:
    """Mask an email address for logging: ``us***@example.com``."""
    email = str(email or "").strip()
    if "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    visible = min(2, len(local))
    return f"{local[:visible]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Mask a phone number for logging: ``+*****1234``."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) <= 4:
        return str(phone or "***")
    return f"+{'*' * (len(digits) - 4)}{digits[-4:]}"
