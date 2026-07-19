"""Regression tests for the conftest DB-isolation guard itself.

api/routers/auth.py uses services.auth_service.get_auth_service() directly,
without ever importing web_server. The guard's singleton reset used to run
only via web_server, so an AuthService created while web_server was absent
from sys.modules survived into later tests holding repos bound to a previous
test's deleted temp sqlite — surfacing as OperationalError("unable to open
database file") in whichever auth test ran next (order-dependent, flaky).

These two tests must run in definition order in the same process: the first
creates the singleton under its own guard DB; the second only passes if the
guard rebuilt it against the new guard DB.
"""

from __future__ import annotations

from services.auth_service import get_auth_service


class TestAuthServiceSingletonIsolation:
    _EMAIL = "guard-isolation@example.com"

    def test_singleton_created_under_first_guard_db(self) -> None:
        user = get_auth_service().create_user_only(email=self._EMAIL, password="Str0ng!Passw0rd")
        assert user["email"] == self._EMAIL

    def test_next_test_gets_fresh_working_auth_service(self) -> None:
        # Stale singleton → repos point at the previous test's deleted temp
        # sqlite → OperationalError. Shared DB → duplicate email → ValueError.
        # Only a properly reset singleton on a fresh guard DB passes.
        user = get_auth_service().create_user_only(email=self._EMAIL, password="Str0ng!Passw0rd")
        assert user["email"] == self._EMAIL


class TestPerRequestRepositoryIsolation:
    """OtpRepository/SpotifyTokenRepository are constructed per request. They
    must bind to the guard-managed shared connection, not to a connection built
    from settings.database_url — the settings singleton freezes DATABASE_URL at
    first import, so under the test guard it points at a long-deleted temp
    sqlite (OperationalError: unable to open database file), and in any process
    it silently builds a brand-new engine per instantiation."""

    def test_otp_repository_binds_shared_connection(self) -> None:
        from database.connection import get_shared_connection
        from database.repositories import OtpRepository

        repo = OtpRepository()
        assert repo._db is get_shared_connection()
        assert repo.cleanup_expired() >= 0

    def test_spotify_token_repository_binds_shared_connection(self) -> None:
        from database.connection import get_shared_connection
        from database.repositories import SpotifyTokenRepository

        repo = SpotifyTokenRepository()
        assert repo._db is get_shared_connection()
        assert repo.get("guard-isolation-user") is None
