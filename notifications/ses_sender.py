"""AWS SES email sender for Smart Bed AI.

Parallel to the existing SendGrid-based EmailService, using AWS SES
as the transport.  Supports plain-text and HTML bodies, and raw
multipart messages (for PDF attachments).

Public API
----------
SESSender(region, from_email, access_key, secret_key)
    .send(to, subject, body_text, body_html, attachments) -> bool

build_ses_sender_from_settings() -> SESSender | None
"""

from __future__ import annotations

import base64
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

logger = logging.getLogger("notifications.ses_sender")

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False


class SESSender:
    """Send transactional emails through AWS SES."""

    def __init__(
        self,
        *,
        region: str = "us-east-1",
        from_email: str,
        from_name: str = "Danah Smart Bed",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        if not _BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is not installed — pip install boto3")

        self._from_email = str(from_email).strip()
        self._from_name = str(from_name).strip()

        session_kwargs: dict[str, Any] = {}
        if access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key

        self._ses = boto3.client(
            "ses", region_name=str(region).strip() or "us-east-1", **session_kwargs
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(
        self,
        to: str | list[str],
        subject: str,
        body_text: str = "",
        body_html: str = "",
        attachments: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send an email via SES.

        attachments: list of {"filename": str, "data": bytes, "content_type": str}
        Returns True on success.
        """
        recipients = [to] if isinstance(to, str) else list(to)
        if not recipients or not subject:
            return False

        try:
            if attachments:
                return self._send_raw(recipients, subject, body_text, body_html, attachments)
            return self._send_simple(recipients, subject, body_text, body_html)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("SES send failed to=%s error=%s", recipients, exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_simple(
        self,
        recipients: list[str],
        subject: str,
        body_text: str,
        body_html: str,
    ) -> bool:
        body: dict[str, Any] = {}
        if body_text:
            body["Text"] = {"Data": body_text, "Charset": "UTF-8"}
        if body_html:
            body["Html"] = {"Data": body_html, "Charset": "UTF-8"}
        if not body:
            return False

        self._ses.send_email(
            Source=f"{self._from_name} <{self._from_email}>",
            Destination={"ToAddresses": recipients},
            Message={
                "Subject": {"Data": str(subject), "Charset": "UTF-8"},
                "Body": body,
            },
        )
        logger.info("SES email sent to %s subject=%r", recipients, subject)
        return True

    def _send_raw(
        self,
        recipients: list[str],
        subject: str,
        body_text: str,
        body_html: str,
        attachments: list[dict[str, Any]],
    ) -> bool:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"{self._from_name} <{self._from_email}>"
        msg["To"] = ", ".join(recipients)

        alt = MIMEMultipart("alternative")
        if body_text:
            alt.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)

        for att in attachments:
            filename = str(att.get("filename", "attachment"))
            data = att.get("data", b"")
            if not isinstance(data, (bytes, bytearray)):
                continue
            part = MIMEApplication(bytes(data))
            part.add_header("Content-Disposition", "attachment", filename=filename)
            content_type = str(att.get("content_type", "application/octet-stream"))
            part.add_header("Content-Type", content_type)
            msg.attach(part)

        self._ses.send_raw_email(
            Source=f"{self._from_name} <{self._from_email}>",
            Destinations=recipients,
            RawMessage={"Data": msg.as_bytes()},
        )
        logger.info("SES raw email (with attachments) sent to %s", recipients)
        return True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_ses_sender_from_settings() -> "SESSender | None":
    """Build an SESSender from config/settings.py. Returns None if not configured."""
    if not _BOTO3_AVAILABLE:
        logger.warning("boto3 not installed — SES unavailable")
        return None

    try:
        from config.settings import settings

        from_email = str(getattr(settings, "aws_ses_from_email", "") or "").strip()
        if not from_email:
            return None
        return SESSender(
            region=str(getattr(settings, "aws_region", "us-east-1") or "us-east-1"),
            from_email=from_email,
            from_name=str(
                getattr(settings, "aws_ses_from_name", "Danah Smart Bed") or "Danah Smart Bed"
            ),
            access_key=str(getattr(settings, "aws_access_key_id", "") or ""),
            secret_key=str(getattr(settings, "aws_secret_access_key", "") or ""),
        )
    except Exception as exc:
        logger.warning("SES sender init failed: %s", exc)
        return None
