"""Pre-launch secret checker for the Danah Smart Bed API (Railway).

Usage:

    python scripts/check_production_secrets.py

Prints one line per required secret (present / missing + what breaks) and a
final verdict: "READY TO LAUNCH" or "NOT READY — fix the above first".
Exit code 0 = ready, 1 = not ready, so it can gate CI or a Railway
pre-deploy command.

Deliberately does NOT import config.settings: a broken SECRET_KEY makes that
import raise before any report could print. Instead this reads the same
sources the app reads (.env via python-dotenv, then os.environ) and mirrors
the checks in config.settings.validate_production_secrets() /
enforce_production_secrets() — keep the two in sync when adding secrets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # project root

# Mirror of the unsafe-default set in config.settings
_UNSAFE_SECRET_KEYS = {"change-me-in-production", "secret", "changeme", "development", ""}
_SECRET_KEY_MIN_LENGTH = 32


def _load_env() -> None:
    """Load .env exactly like config.settings does (best effort)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass


def _present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def _secret_key_ok(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return value not in _UNSAFE_SECRET_KEYS and len(value) >= _SECRET_KEY_MIN_LENGTH


# (env var, check function, what breaks if missing)
# These are the secrets enforce_production_secrets() refuses to boot without
# when DANAH_ENV=production.
REQUIRED_SECRETS: list[tuple[str, object, str]] = [
    (
        "SECRET_KEY",
        _secret_key_ok,
        "JWT signing key (auth/jwt_handler.py). Missing/weak = every signup, "
        "login, and token check fails — and with the known default, anyone "
        "can forge valid tokens for any account.",
    ),
    (
        "DATABASE_URL",
        _present,
        "Neon Postgres connection. Missing = no users, no auth, no "
        "billing/admin state — the app would boot but every DB-backed "
        "endpoint fails at runtime.",
    ),
    (
        "PAYPAL_CLIENT_ID",
        _present,
        "PayPal OAuth client ID. Missing = billing unavailable — checkout "
        "can never start, subscriptions fail.",
    ),
    (
        "PAYPAL_CLIENT_SECRET",
        _present,
        "PayPal OAuth client secret. Missing = PayPal token requests fail at "
        "runtime, so subscriptions fail even with the client ID present.",
    ),
    (
        "DEVICE_FACTORY_SECRET",
        _present,
        "/v1/device/auth returns 503 — beds cannot authenticate or pair, so "
        "app-to-bed commands are dead.",
    ),
    (
        "DEEPGRAM_API_KEY",
        _present,
        "Voice STT/TTS unavailable — voice features degrade to fallback "
        "responses.",
    ),
    (
        "AWS_SES_FROM_EMAIL",
        _present,
        "Email notifications (password reset, reports) unavailable.",
    ),
]

# Non-blocking but strongly recommended before launch. Missing = degraded
# mode, printed as a warning without affecting the verdict.
RECOMMENDED_SECRETS: list[tuple[str, str]] = [
    (
        "REDIS_URL",
        "Degraded mode: in-memory rate limits, no brute-force lockout, no "
        "background jobs.",
    ),
    ("SENTRY_DSN", "No error tracking in production."),
    (
        "PAYPAL_WEBHOOK_ID",
        "PayPal webhook signature verification fails — subscription "
        "activation/cancellation events are not processed.",
    ),
    (
        "OPENAI_API_KEY",
        "Direct GPT chat route disabled — chat falls back to backend/offline "
        "responses.",
    ),
    (
        "FIREBASE_CREDENTIALS_JSON",
        "Push notifications (FCM) disabled (FIREBASE_CREDENTIALS_PATH also "
        "accepted).",
    ),
]


def main() -> int:
    # Windows consoles often default to a legacy codepage that cannot print
    # the check-mark emoji; force UTF-8 where supported.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    _load_env()

    env_name = os.getenv("DANAH_ENV", "development").lower()
    print(f"Danah Smart Bed — production secret preflight (DANAH_ENV={env_name})")
    print("=" * 72)

    missing = 0
    for name, check, impact in REQUIRED_SECRETS:
        if check(name):  # type: ignore[operator]
            print(f"✅ {name}")
        else:
            missing += 1
            print(f"❌ {name} — {impact}")

    print("-" * 72)
    for name, impact in RECOMMENDED_SECRETS:
        # FIREBASE_CREDENTIALS_JSON has a file-path alternative
        alt_ok = name == "FIREBASE_CREDENTIALS_JSON" and _present("FIREBASE_CREDENTIALS_PATH")
        if _present(name) or alt_ok:
            print(f"✅ {name} (recommended)")
        else:
            print(f"⚠️  {name} (recommended) — {impact}")

    print("=" * 72)
    if missing == 0:
        print("READY TO LAUNCH")
        return 0
    print(f"NOT READY — fix the above first ({missing} required secret(s) missing)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
