"""Global test guards.

Tests must NEVER touch the real DATABASE_URL. config.settings calls
load_dotenv() at import, so the developer's .env (live Neon Postgres) leaks
into os.environ — any test that builds a store or repository without
isolating its own DB would otherwise read from and write to production.
(Found the hard way on 2026-07-19: billing tests leaked webhook receipts and
checkout rows into Neon; only an FK violation stopped the subscription sync.)

The guard is function-scoped: every test gets a fresh throwaway sqlite and a
reset shared connection, so fixed test ids (WH-EVENT-DEDUPE-1, usr_local, …)
can never collide across tests through a shared DB either. Tests that manage
their own DATABASE_URL still override this inside their own scope.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Several test modules import sibling helpers bare ("from env_isolation import
# ..."). Introducing this conftest changed pytest's sys.path setup for them —
# guarantee the tests directory is importable either way.
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# freeze_time scans every loaded module for time attributes; on lazy-import
# giants (transformers etc.) that scan triggers recursive imports mid-GC and
# crashes the interpreter with a stack overflow on py3.14 (test_frozen_time
# after any file that pulls in web_server). No test freezes time inside these
# libraries — skip scanning them.
try:
    import freezegun

    freezegun.configure(
        extend_ignore_list=[
            "transformers",
            "torch",
            "tensorflow",
            "chromadb",
            "litellm",
            "sentence_transformers",
        ]
    )
except ImportError:  # pragma: no cover - freezegun is a test dependency
    pass


def _reset_web_server_singletons() -> None:
    """web_server caches repo/connection singletons; after the guard repoints
    DATABASE_URL they would keep serving the previous test's deleted sqlite."""
    ws = sys.modules.get("web_server")
    if ws is not None:
        from tests.env_isolation import reset_web_server_db_singletons

        reset_web_server_db_singletons(ws)
    # api/routers/auth.py uses the AuthService singleton without importing
    # web_server, so it must be reset independently — the reset above only
    # covers it transitively when web_server happens to be loaded.
    if "services.auth_service" in sys.modules:
        from tests.env_isolation import reset_auth_service_singleton

        reset_auth_service_singleton()


@pytest.fixture(autouse=True)
def _no_production_database():
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    url = f"sqlite:///{(Path(tmp.name) / 'guard_test.sqlite3').as_posix()}"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url

    from database.connection import get_shared_connection, reset_shared_connection

    _reset_web_server_singletons()
    get_shared_connection().create_tables()
    try:
        yield
    finally:
        _reset_web_server_singletons()
        reset_shared_connection()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        tmp.cleanup()
