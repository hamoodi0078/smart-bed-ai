"""PayPal Subscriptions API provider used by the billing service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests


class PayPalProviderError(RuntimeError):
    """Raised when PayPal rejects or cannot fulfill a request."""


@dataclass(frozen=True)
class PayPalSubscriptionSession:
    subscription_id: str
    plan_id: str
    status: str
    approve_url: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class PayPalSubscriptionDetails:
    subscription_id: str
    plan_id: str
    status: str
    next_billing_time: str
    status_update_time: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class PayPalWebhookVerification:
    verified: bool
    status: str
    raw: dict[str, Any]


class PayPalProvider:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        api_base: str,
        webhook_id: str,
        brand_name: str,
        currency_code: str,
        timeout_seconds: int = 20,
    ) -> None:
        self.client_id = str(client_id or "").strip()
        self.client_secret = str(client_secret or "").strip()
        self.api_base = str(api_base or "https://api-m.sandbox.paypal.com").rstrip("/")
        self.webhook_id = str(webhook_id or "").strip()
        self.brand_name = str(brand_name or "Danah Smart Bed").strip() or "Danah Smart Bed"
        self.currency_code = str(currency_code or "USD").strip().upper() or "USD"
        self.timeout_seconds = max(5, int(timeout_seconds or 20))

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def environment(self) -> str:
        return "sandbox" if "sandbox" in self.api_base.lower() else "live"

    def create_subscription(
        self,
        *,
        session_id: str,
        plan_id: str,
        return_url: str,
        cancel_url: str,
        payer_email: str = "",
    ) -> PayPalSubscriptionSession:
        plan_key = str(plan_id or "").strip()
        if not plan_key:
            raise PayPalProviderError("plan_id is required to create a PayPal subscription.")

        payload: dict[str, Any] = {
            "plan_id": plan_key,
            "custom_id": str(session_id or "").strip(),
            "application_context": {
                "brand_name": self.brand_name,
                "user_action": "SUBSCRIBE_NOW",
                "shipping_preference": "NO_SHIPPING",
                "return_url": return_url,
                "cancel_url": cancel_url,
                "payment_method": {
                    "payer_selected": "PAYPAL",
                    "payee_preferred": "IMMEDIATE_PAYMENT_REQUIRED",
                },
            },
        }
        email = str(payer_email or "").strip()
        if email:
            payload["subscriber"] = {"email_address": email}

        data = self._request_json(
            "POST",
            "/v1/billing/subscriptions",
            json=payload,
            headers={"PayPal-Request-Id": f"subscription-{session_id}"},
        )
        subscription_id = str(data.get("id", "") or "").strip()
        approve_url = self._extract_approve_url(data)
        if not subscription_id or not approve_url:
            raise PayPalProviderError(
                "PayPal subscription response did not contain a subscription ID and approval link."
            )
        return PayPalSubscriptionSession(
            subscription_id=subscription_id,
            plan_id=str(data.get("plan_id", "") or plan_key).strip(),
            status=str(data.get("status", "") or "").strip(),
            approve_url=approve_url,
            raw=data,
        )

    def get_subscription_details(self, subscription_id: str) -> PayPalSubscriptionDetails:
        subscription_key = str(subscription_id or "").strip()
        if not subscription_key:
            raise PayPalProviderError("subscription_id is required to fetch PayPal subscription details.")

        data = self._request_json(
            "GET",
            f"/v1/billing/subscriptions/{subscription_key}",
        )
        billing_info = data.get("billing_info", {})
        next_billing_time = ""
        if isinstance(billing_info, dict):
            next_billing_time = str(billing_info.get("next_billing_time", "") or "").strip()
        return PayPalSubscriptionDetails(
            subscription_id=subscription_key,
            plan_id=str(data.get("plan_id", "") or "").strip(),
            status=str(data.get("status", "") or "").strip(),
            next_billing_time=next_billing_time,
            status_update_time=str(data.get("status_update_time", "") or "").strip(),
            raw=data,
        )

    def suspend_subscription(self, subscription_id: str, *, reason: str = "Paused by user") -> None:
        subscription_key = str(subscription_id or "").strip()
        if not subscription_key:
            raise PayPalProviderError("subscription_id is required to suspend a subscription.")
        self._request_json(
            "POST",
            f"/v1/billing/subscriptions/{subscription_key}/suspend",
            json={"reason": str(reason or "Paused by user").strip() or "Paused by user"},
            headers={"PayPal-Request-Id": f"suspend-{subscription_key}"},
        )

    def cancel_subscription(self, subscription_id: str, *, reason: str = "Cancelled by user") -> None:
        subscription_key = str(subscription_id or "").strip()
        if not subscription_key:
            raise PayPalProviderError("subscription_id is required to cancel a subscription.")
        self._request_json(
            "POST",
            f"/v1/billing/subscriptions/{subscription_key}/cancel",
            json={"reason": str(reason or "Cancelled by user").strip() or "Cancelled by user"},
            headers={"PayPal-Request-Id": f"cancel-{subscription_key}"},
        )

    def verify_webhook_signature(
        self,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> PayPalWebhookVerification:
        if not self.webhook_id:
            raise PayPalProviderError("PAYPAL_WEBHOOK_ID is required to verify webhook signatures.")

        verification_payload = {
            "auth_algo": self._header(headers, "paypal-auth-algo"),
            "cert_url": self._header(headers, "paypal-cert-url"),
            "transmission_id": self._header(headers, "paypal-transmission-id"),
            "transmission_sig": self._header(headers, "paypal-transmission-sig"),
            "transmission_time": self._header(headers, "paypal-transmission-time"),
            "webhook_id": self.webhook_id,
            "webhook_event": dict(payload),
        }
        data = self._request_json(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json=verification_payload,
        )
        status_value = str(data.get("verification_status", "") or "").strip().upper()
        return PayPalWebhookVerification(
            verified=status_value == "SUCCESS",
            status=status_value,
            raw=data,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if headers:
            request_headers.update({str(key): str(value) for key, value in headers.items()})
        url = f"{self.api_base}{path}"
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=request_headers,
                json=json,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PayPalProviderError(f"Unable to reach PayPal at {url}: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            raise PayPalProviderError(
                f"PayPal request failed ({response.status_code}): {detail or 'no response body'}"
            )

        if response.status_code == 204:
            return {}

        try:
            data = response.json()
        except ValueError as exc:
            raise PayPalProviderError("PayPal returned a non-JSON response.") from exc
        if not isinstance(data, dict):
            raise PayPalProviderError("PayPal returned an unexpected payload shape.")
        return data

    def _access_token(self) -> str:
        if not self.configured:
            raise PayPalProviderError("PayPal credentials are not configured.")

        try:
            response = requests.post(
                f"{self.api_base}/v1/oauth2/token",
                data={"grant_type": "client_credentials"},
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en_US",
                },
                auth=(self.client_id, self.client_secret),
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PayPalProviderError(f"Unable to request a PayPal access token: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            raise PayPalProviderError(
                f"PayPal OAuth failed ({response.status_code}): {detail or 'no response body'}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PayPalProviderError("PayPal OAuth returned a non-JSON response.") from exc

        token = str(data.get("access_token", "") or "").strip()
        if not token:
            raise PayPalProviderError("PayPal OAuth response did not include an access token.")
        return token

    @staticmethod
    def _extract_approve_url(payload: Mapping[str, Any]) -> str:
        links = payload.get("links", [])
        if not isinstance(links, list):
            return ""
        for item in links:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("rel", "") or "").strip().lower()
            href = str(item.get("href", "") or "").strip()
            if rel in {"approve", "payer-action"} and href:
                return href
        return ""

    @staticmethod
    def _header(headers: Mapping[str, str], key: str) -> str:
        for header_name, value in headers.items():
            if str(header_name).strip().lower() == key:
                return str(value or "").strip()
        return ""
