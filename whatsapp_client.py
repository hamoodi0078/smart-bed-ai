"""WhatsApp messaging client using the Facebook Graph API.

Requires environment variables:
  WHATSAPP_PHONE_NUMBER_ID  — your WhatsApp Business phone number ID
  WHATSAPP_ACCESS_TOKEN     — long-lived access token for the Graph API
"""

from __future__ import annotations

import json
import os

import requests
from loguru import logger

WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_API_VERSION: str = os.getenv("WHATSAPP_API_VERSION", "v20.0")
WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")

_configured: bool = bool(WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN)

if not _configured:
    logger.warning(
        "WhatsApp client not configured — set WHATSAPP_PHONE_NUMBER_ID and "
        "WHATSAPP_ACCESS_TOKEN in your .env file to enable WhatsApp messaging."
    )


def _api_url() -> str:
    return f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def is_configured() -> bool:
    """Return True if the WhatsApp client has valid credentials."""
    return _configured


def send_template(
    to_number: str,
    template_name: str = "hello_world",
    language_code: str = "en_US",
) -> dict:
    """Send a WhatsApp template message.

    Parameters
    ----------
    to_number:
        Recipient in full international format, e.g. '+965XXXXXXXX'.
    template_name:
        Name of the approved WhatsApp template to send.
    language_code:
        BCP-47 language code for the template.

    Returns
    -------
    dict  — Graph API response body on success, or an error dict.
    """
    if not _configured:
        logger.error("WhatsApp send_template called but client is not configured.")
        return {"ok": False, "error": "whatsapp_not_configured"}

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }

    logger.info("WhatsApp: sending '{}' template to {}", template_name, to_number)
    try:
        response = requests.post(_api_url(), headers=headers, json=body, timeout=20)
    except requests.RequestException as exc:
        logger.error("WhatsApp request failed: {}", exc)
        return {"ok": False, "error": str(exc)}

    if response.ok:
        try:
            data = response.json()
            logger.info("WhatsApp: message sent successfully: {}", json.dumps(data))
            return data
        except ValueError:
            logger.warning("WhatsApp: message sent but response was not valid JSON.")
            return {"ok": True, "status_code": response.status_code, "text": response.text}

    logger.error("WhatsApp API error {}: {}", response.status_code, response.text)
    return {"ok": False, "status_code": response.status_code, "text": response.text}


def send_hello_world(to_number: str) -> dict:
    """Convenience wrapper — sends the default 'hello_world' template."""
    return send_template(to_number, template_name="hello_world")
