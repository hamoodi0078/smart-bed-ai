from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from contextlib import contextmanager

from database.connection import DatabaseConnection
from database.repositories import UserRepository
from notifications.email_service import EmailService


class _SessionBackedDb:
    def __init__(self, session):
        self._session = session

    def create_tables(self) -> None:
        return None

    @contextmanager
    def get_session(self):
        yield self._session


def main() -> None:
    db = DatabaseConnection()

    with db.get_session() as session:
        user_repo = UserRepository(_SessionBackedDb(session))

        email = "danahabuhalifa@gmail.com"
        user = user_repo.get_user_by_email(email)
        if user is None:
            user = user_repo.create_user(email=email, password_hash="dummy", full_name="Hamoud")
            session.commit()
            print("Created user:", user.id)
        else:
            print("Using existing user:", user.id)

    service = EmailService(db=db)
    ok = service.send_daily_summary_for_user(str(user.id))
    print("Daily summary success?", ok)


if __name__ == "__main__":
    main()
