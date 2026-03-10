import os
import json
import requests

WHATSAPP_PHONE_NUMBER_ID = "1012811618583799"
WHATSAPP_API_VERSION = "v20.0"
WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
if not WHATSAPP_ACCESS_TOKEN:
    raise RuntimeError(
        "Missing WHATSAPP_ACCESS_TOKEN. Set the environment variable before using whatsapp_client."
    )


def send_hello_world(to_number: str) -> dict:
    """
    Send the 'hello_world' WhatsApp template to the given phone number.
    to_number must be in full international format, e.g. '+965XXXXXXXX'.
    """
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"},
        },
    }

    print(f"[WhatsApp] Sending hello_world template to {to_number}")
    try:
        response = requests.post(
            WHATSAPP_API_URL,
            headers=headers,
            json=payload,
            timeout=20,
        )
    except requests.RequestException as exc:
        print(f"[WhatsApp] Request failed: {exc}")
        return {"status_code": None, "text": str(exc)}

    if response.ok:
        try:
            data = response.json()
            print(f"[WhatsApp] Message sent successfully: {json.dumps(data)}")
            return data
        except ValueError:
            print("[WhatsApp] Message sent, but response was not valid JSON.")
            return {"status_code": response.status_code, "text": response.text}

    print(f"[WhatsApp] API error {response.status_code}: {response.text}")
    return {"status_code": response.status_code, "text": response.text}
