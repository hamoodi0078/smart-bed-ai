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
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_production_database():
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    url = f"sqlite:///{(Path(tmp.name) / 'guard_test.sqlite3').as_posix()}"
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url

    from database.connection import get_shared_connection, reset_shared_connection

    reset_shared_connection()
    get_shared_connection().create_tables()
    try:
        yield
    finally:
        reset_shared_connection()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        tmp.cleanup()
