from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional

from loguru import logger as _module_log

from core.http_client import http

from database.connection import DatabaseConnection
from database.repositories import EventRepository, SleepSessionRepository, UserRepository
from notifications.summaries import build_daily_summary, build_monthly_summary
from time_utils import utcnow


class _SessionBoundDatabase:
    def __init__(self, session):
        self._session = session

    def create_tables(self) -> None:
        return None

    @contextmanager
    def get_session(self):
        yield self._session


class EmailService:
    SENDGRID_SEND_ENDPOINT = "https://api.sendgrid.com/v3/mail/send"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        from_email: Optional[str] = None,
        db: Optional[DatabaseConnection] = None,
    ):
        self.api_key = str(api_key or os.getenv("SENDGRID_API_KEY", "")).strip()
        self.from_email = str(from_email or os.getenv("EMAIL_FROM", "")).strip()
        self.db = db or DatabaseConnection()
        self.logger = _module_log
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY is required")
        if not self.from_email:
            raise ValueError("EMAIL_FROM is required")

    def _send_raw_email(self, to_email: str, subject: str, plain_text: str) -> bool:
        payload = {
            "personalizations": [{"to": [{"email": str(to_email or "").strip()}]}],
            "from": {"email": self.from_email, "name": "Manues Smart Bed"},
            "subject": str(subject or "").strip(),
            "content": [{"type": "text/plain", "value": str(plain_text or "")}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = http.post(
                self.SENDGRID_SEND_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=15,
            )
        except Exception as exc:
            self.logger.warning("SendGrid request failed: {}", exc)
            return False

        if 200 <= int(response.status_code) < 300:
            return True

        self.logger.warning(
            "SendGrid rejected email status={} body={}",
            response.status_code,
            response.text[:200],
        )
        return False

    def send_daily_summary_for_user(self, user_id: str) -> bool:
        try:
            with self.db.get_session() as session:
                bound_db = _SessionBoundDatabase(session)
                user_repo = UserRepository(db=bound_db)
                event_repo = EventRepository(db=bound_db)
                sleep_repo = SleepSessionRepository(db=bound_db)

                user = user_repo.get_user_by_id(user_id)
                if user is None:
                    return False

                to_email = str(user.email or "").strip()
                if not to_email:
                    return False

                summary = build_daily_summary(
                    user.id,
                    event_repo=event_repo,
                    sleep_repo=sleep_repo,
                )
                subject = str(summary.get("subject") or "").strip()
                plain_text = str(summary.get("plain_text") or "")
        except Exception as exc:
            self.logger.warning("Daily summary build failed user_id=%s error=%s", user_id, exc)
            return False

        return self._send_raw_email(to_email, subject, plain_text)

    def send_monthly_summary_for_user(self, user_id: str, year: int, month: int) -> bool:
        try:
            with self.db.get_session() as session:
                bound_db = _SessionBoundDatabase(session)
                user_repo = UserRepository(db=bound_db)
                event_repo = EventRepository(db=bound_db)
                sleep_repo = SleepSessionRepository(db=bound_db)

                user = user_repo.get_user_by_id(user_id)
                if user is None:
                    return False

                to_email = str(user.email or "").strip()
                if not to_email:
                    return False

                summary = build_monthly_summary(
                    user.id,
                    int(year),
                    int(month),
                    event_repo=event_repo,
                    sleep_repo=sleep_repo,
                )
                subject = str(summary.get("subject") or "").strip()
                plain_text = str(summary.get("plain_text") or "")
        except Exception as exc:
            self.logger.warning(
                "Monthly summary build failed user_id=%s year=%s month=%s error=%s",
                user_id,
                year,
                month,
                exc,
            )
            return False

        return self._send_raw_email(to_email, subject, plain_text)

    def send_daily_summaries_for_all_users(self) -> int:
        batch_started_at = utcnow()
        self.logger.info("Daily email summary batch started at %s", batch_started_at.isoformat())
        try:
            with self.db.get_session() as session:
                user_repo = UserRepository(db=_SessionBoundDatabase(session))
                users = user_repo.list_all(limit=1000)
        except Exception as exc:
            self.logger.warning("Daily email summary batch failed while loading users: %s", exc)
            return 0

        success_count = 0
        for user in users:
            to_email = str(user.email or "").strip()
            if not to_email:
                continue
            try:
                if self.send_daily_summary_for_user(user.id):
                    success_count += 1
            except Exception as exc:
                self.logger.warning(
                    "Daily email summary send failed user_id=%s error=%s", user.id, exc
                )

        self.logger.info(
            "Daily email summary batch finished at %s successes=%s attempted=%s",
            utcnow().isoformat(),
            success_count,
            len(users),
        )
        return success_count

    def send_monthly_summaries_for_all_users(self, year: int, month: int) -> int:
        batch_started_at = utcnow()
        self.logger.info(
            "Monthly email summary batch started at %s year=%s month=%s",
            batch_started_at.isoformat(),
            year,
            month,
        )
        try:
            with self.db.get_session() as session:
                user_repo = UserRepository(db=_SessionBoundDatabase(session))
                users = user_repo.list_all(limit=1000)
        except Exception as exc:
            self.logger.warning("Monthly email summary batch failed while loading users: %s", exc)
            return 0

        success_count = 0
        for user in users:
            to_email = str(user.email or "").strip()
            if not to_email:
                continue
            try:
                if self.send_monthly_summary_for_user(user.id, int(year), int(month)):
                    success_count += 1
            except Exception as exc:
                self.logger.warning(
                    "Monthly email summary send failed user_id=%s year=%s month=%s error=%s",
                    user.id,
                    year,
                    month,
                    exc,
                )

        self.logger.info(
            "Monthly email summary batch finished at %s year=%s month=%s successes=%s attempted=%s",
            utcnow().isoformat(),
            year,
            month,
            success_count,
            len(users),
        )
        return success_count
