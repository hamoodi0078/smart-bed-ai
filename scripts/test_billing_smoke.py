"""Manual smoke test: billing state survives a service restart (Plan 8).

Usage (from the repo root):
    python scripts/test_billing_smoke.py

What it does:
  a) creates a throwaway test user in the users table
  b) creates a SubscriptionRecord row (tier="smart", status="active")
  c) reads it back and confirms it is there
  d) simulates a service restart: disposes every pooled connection and
     builds a brand-new engine + pool (what a Railway redeploy does to
     the DB layer — process memory and the JSON file are also lost, but
     Postgres is the durable copy this script verifies)
  e) reads the row back through the NEW connection and confirms it survived
  f) cleans up (deletes the subscription row + the test user)
  g) prints [PASS]/[FAIL] per step and exits 0 only if every step passed

Targets DATABASE_URL from the environment / .env (same resolution rules as
DatabaseConnection). Only touches rows it created itself, keyed by a random
per-run UUID, so it is safe to run against a shared database.
"""

from __future__ import annotations

import sys
import traceback
import uuid
from pathlib import Path

# Make project imports resolve whether run from repo root or scripts/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from sqlalchemy import select  # noqa: E402

from database.connection import DatabaseConnection  # noqa: E402
from database.models import SubscriptionRecord, User  # noqa: E402

_MARKER = uuid.uuid4().hex[:12]
TEST_USER_ID = f"smoke-{_MARKER}"  # fits users.id String(36)
TEST_EMAIL = f"billing-smoke-{_MARKER}@smoke.invalid"

_results: list[bool] = []


def _step(label: str, ok: bool, detail: str = "") -> bool:
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {label}"
    if detail:
        line += f" -- {detail}"
    print(line)
    _results.append(ok)
    return ok


def _read_subscription(conn: DatabaseConnection) -> SubscriptionRecord | None:
    with conn.get_session() as session:
        return session.execute(
            select(SubscriptionRecord)
            .where(SubscriptionRecord.user_id == TEST_USER_ID)
            .limit(1)
        ).scalar_one_or_none()


def _cleanup(conn: DatabaseConnection) -> tuple[int, int]:
    """Delete only the rows this run created. Returns (subs_deleted, users_deleted)."""
    subs_deleted = users_deleted = 0
    with conn.get_session() as session:
        rows = session.scalars(
            select(SubscriptionRecord).where(SubscriptionRecord.user_id == TEST_USER_ID)
        ).all()
        for row in rows:
            session.delete(row)
            subs_deleted += 1
        user = session.get(User, TEST_USER_ID)
        if user is not None:
            session.delete(user)
            users_deleted += 1
    return subs_deleted, users_deleted


def main() -> int:
    conn = DatabaseConnection()
    print(f"Target database: {conn._safe_url()}")
    if conn.database_url.lower().startswith("sqlite"):
        print(
            "WARNING: DATABASE_URL is not set -- running against the SQLite "
            "fallback. This does NOT prove Postgres/Railway durability."
        )
    conn.create_tables()  # no-op when the schema already exists

    try:
        # a) create test user -------------------------------------------------
        try:
            with conn.get_session() as session:
                session.add(
                    User(
                        id=TEST_USER_ID,
                        email=TEST_EMAIL,
                        password_hash="smoke-test-not-a-real-hash",
                        full_name="Billing Smoke Test",
                    )
                )
            _step("a) create test user", True, f"id={TEST_USER_ID}")
        except Exception:
            _step("a) create test user", False, traceback.format_exc(limit=1).strip())
            return 1

        # b) create SubscriptionRecord ----------------------------------------
        try:
            with conn.get_session() as session:
                session.add(
                    SubscriptionRecord(
                        user_id=TEST_USER_ID,
                        tier="smart",
                        status="active",
                    )
                )
            _step('b) insert SubscriptionRecord(tier="smart", status="active")', True)
        except Exception:
            _step("b) insert SubscriptionRecord", False, traceback.format_exc(limit=1).strip())
            return 1

        # c) read back --------------------------------------------------------
        row = _read_subscription(conn)
        ok = row is not None and row.tier == "smart" and row.status == "active"
        detail = (
            f"tier={row.tier!r} status={row.status!r}" if row is not None else "row not found"
        )
        if not _step("c) read back subscription before restart", ok, detail):
            return 1

        # d) simulate service restart -----------------------------------------
        try:
            conn.engine.dispose()  # closes every pooled connection ("shutdown")
            conn = DatabaseConnection()  # brand-new engine + pool ("boot")
            _step("d) simulate restart (dispose pool, reconnect fresh engine)", True)
        except Exception:
            _step("d) simulate restart", False, traceback.format_exc(limit=1).strip())
            return 1

        # e) read back through the new connection ------------------------------
        row = _read_subscription(conn)
        ok = row is not None and row.tier == "smart" and row.status == "active"
        detail = (
            f"tier={row.tier!r} status={row.status!r}"
            if row is not None
            else "row NOT found after reconnect -- data did not survive"
        )
        if not _step("e) subscription survived the restart", ok, detail):
            return 1

        return 0
    finally:
        # f) cleanup -- always runs, even when an earlier step failed ----------
        try:
            subs_deleted, users_deleted = _cleanup(conn)
            leftover = _read_subscription(conn)
            with conn.get_session() as session:
                leftover_user = session.get(User, TEST_USER_ID)
            clean = leftover is None and leftover_user is None
            _step(
                "f) cleanup (delete test subscription + user)",
                clean,
                f"subscriptions deleted={subs_deleted}, users deleted={users_deleted}",
            )
        except Exception:
            _step("f) cleanup", False, traceback.format_exc(limit=1).strip())

        # g) summary ------------------------------------------------------------
        total = len(_results)
        passed = sum(_results)
        overall = "PASS" if passed == total else "FAIL"
        print(f"\n{overall}: {passed}/{total} steps passed")


if __name__ == "__main__":
    exit_code = main()
    sys.exit(0 if (exit_code == 0 and all(_results)) else 1)
