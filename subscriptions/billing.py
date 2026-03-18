"""Billing service that coordinates local checkout state with payment providers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping
from urllib.parse import urlencode

from config import settings
from Storage.subscription_store import SubscriptionStore
from time_utils import from_iso, to_iso, utcnow

from .paypal_provider import (
    PayPalProvider,
    PayPalProviderError,
    PayPalSubscriptionDetails,
)


class BillingServiceError(RuntimeError):
    """Raised when billing operations cannot be completed safely."""


@dataclass(frozen=True)
class BillingWebhookResult:
    user_id: str
    event_type: str
    verified: bool
    checkout_session_id: str
    duplicate: bool = False
    replayed: bool = False
    webhook_event_id: str = ""
    transmission_id: str = ""
    idempotency_key: str = ""


class BillingService:
    def __init__(
        self,
        *,
        store: SubscriptionStore,
        app_base_url: str,
        paypal_provider: PayPalProvider | None = None,
        paypal_plan_ids: Mapping[tuple[str, str], str] | None = None,
        paypal_webhook_max_age_seconds: int = 600,
        paypal_webhook_receipt_ttl_seconds: int = 24 * 3600,
    ) -> None:
        self.store = store
        self.app_base_url = str(app_base_url or "").rstrip("/")
        self.paypal_provider = paypal_provider
        self.paypal_webhook_max_age_seconds = max(60, int(paypal_webhook_max_age_seconds or 600))
        self.paypal_webhook_receipt_ttl_seconds = max(
            self.paypal_webhook_max_age_seconds,
            int(paypal_webhook_receipt_ttl_seconds or (24 * 3600)),
        )
        self.paypal_plan_ids = {
            (str(tier).strip().lower(), str(interval).strip().lower()): str(plan_id or "").strip()
            for (tier, interval), plan_id in dict(paypal_plan_ids or {}).items()
            if str(plan_id or "").strip()
        }

    @classmethod
    def from_settings(cls, store: SubscriptionStore) -> "BillingService":
        provider = PayPalProvider(
            client_id=settings.paypal_client_id,
            client_secret=settings.paypal_client_secret,
            api_base=settings.paypal_api_base,
            webhook_id=settings.paypal_webhook_id,
            brand_name=settings.paypal_brand_name,
            currency_code=settings.paypal_currency_code,
            timeout_seconds=settings.paypal_timeout_seconds,
        )
        plan_ids = {
            ("standard", "monthly"): settings.paypal_standard_monthly_plan_id,
            ("standard", "yearly"): settings.paypal_standard_yearly_plan_id,
            ("pro", "monthly"): settings.paypal_pro_monthly_plan_id,
            ("pro", "yearly"): settings.paypal_pro_yearly_plan_id,
        }
        return cls(
            store=store,
            app_base_url=settings.app_base_url,
            paypal_provider=provider,
            paypal_plan_ids=plan_ids,
            paypal_webhook_max_age_seconds=settings.paypal_webhook_max_age_seconds,
            paypal_webhook_receipt_ttl_seconds=settings.paypal_webhook_receipt_ttl_seconds,
        )

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_provider and self.paypal_provider.configured)

    def create_checkout_session(
        self,
        *,
        user_id: str,
        tier: str,
        interval: str,
        return_url: str = "",
        cancel_url: str = "",
        payer_email: str = "",
    ) -> dict[str, Any]:
        checkout = self.store.create_checkout_session(
            user_id=user_id,
            tier=tier,
            interval=interval,
            payment_provider="paypal",
            base_url=self.app_base_url,
        )
        checkout["return_url"] = str(return_url or "").strip()
        checkout["cancel_url"] = str(cancel_url or "").strip()

        plan_id = self._paypal_plan_id(tier=tier, interval=interval)
        if not self.paypal_configured or not plan_id:
            checkout["payment_provider"] = "paypal_local"
            checkout["provider_environment"] = "local_fallback"
            checkout["provider_status"] = "LOCAL_FALLBACK"
            checkout["provider_plan_id"] = plan_id
            self.store.save()
            return checkout

        assert self.paypal_provider is not None
        subscription = self.paypal_provider.create_subscription(
            session_id=str(checkout.get("session_id", "") or ""),
            plan_id=plan_id,
            return_url=self._paypal_return_url(str(checkout.get("session_id", "") or "")),
            cancel_url=self._paypal_cancel_url(str(checkout.get("session_id", "") or "")),
            payer_email=payer_email,
        )
        checkout["approve_url"] = subscription.approve_url
        checkout["provider_subscription_id"] = subscription.subscription_id
        checkout["provider_plan_id"] = subscription.plan_id
        checkout["provider_environment"] = self.paypal_provider.environment
        checkout["provider_currency"] = self.paypal_provider.currency_code
        checkout["provider_status"] = subscription.status
        checkout["status"] = "approval_pending"
        self.store.save()
        return checkout

    def capture_checkout_session(
        self,
        *,
        session_id: str,
        user_id: str,
        payer_id: str = "",
        provider_order_id: str = "",
        provider_subscription_id: str = "",
        raw_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkout = self._require_checkout(session_id=session_id, user_id=user_id)
        if str(checkout.get("status", "") or "").strip().lower() == "completed":
            return checkout

        payload: dict[str, Any] = dict(raw_payload or {})
        subscription_key = self._subscription_key(
            provider_subscription_id=provider_subscription_id,
            provider_order_id=provider_order_id,
            checkout=checkout,
        )
        if self.paypal_configured and subscription_key:
            assert self.paypal_provider is not None
            details = self.paypal_provider.get_subscription_details(subscription_key)
            self._apply_subscription_details(checkout=checkout, details=details)
            payload = {
                **payload,
                "provider_subscription_id": details.subscription_id,
                "provider_plan_id": details.plan_id,
                "provider_status": details.status,
                "next_billing_time": details.next_billing_time,
                "status_update_time": details.status_update_time,
                "resource": deepcopy(details.raw),
            }
            if payer_id:
                payload["payer_id"] = str(payer_id or "").strip()

            normalized_status = details.status.strip().upper()
            if normalized_status in {"ACTIVE", "APPROVED"}:
                return self._mark_checkout_completed(
                    checkout=checkout,
                    user_id=user_id,
                    raw_payload=payload,
                    event_type="billing.subscription.activated",
                )
            checkout["status"] = "approved"
            self.store.apply_billing_webhook(
                event_type="billing.subscription.created",
                user_id=user_id,
                tier=str(checkout.get("tier", "standard") or "standard"),
                interval=str(checkout.get("interval", "monthly") or "monthly"),
                payment_provider="paypal",
                raw_payload=payload,
            )
            self.store.save()
            return checkout

        if str(checkout.get("provider_subscription_id", "") or "").strip():
            raise BillingServiceError("This checkout requires a PayPal subscription approval.")

        if payer_id:
            checkout["payer_id"] = str(payer_id or "").strip()
            payload["payer_id"] = str(payer_id or "").strip()
        return self._mark_checkout_completed(
            checkout=checkout,
            user_id=user_id,
            raw_payload=payload,
            event_type="checkout.completed",
        )

    def cancel_checkout_session(
        self,
        *,
        session_id: str,
        user_id: str,
        reason: str = "cancelled",
    ) -> dict[str, Any]:
        checkout = self._require_checkout(session_id=session_id, user_id=user_id)
        checkout["status"] = "cancelled"
        checkout["provider_status"] = "CANCELLED"
        checkout["cancelled_at"] = self._now_iso()
        checkout["cancel_reason"] = str(reason or "cancelled").strip()
        self.store.save()
        return checkout

    def pause_active_subscription(
        self,
        *,
        user_id: str,
        reason: str = "Paused by user",
    ) -> dict[str, Any]:
        subscription = self.store.get_subscription(user_id)
        provider_subscription_id = str(subscription.get("provider_subscription_id", "") or "").strip()
        if not provider_subscription_id:
            raise BillingServiceError("No active PayPal subscription is linked to this account.")
        if not self.paypal_configured:
            raise BillingServiceError("PayPal is not configured for live subscription actions.")

        assert self.paypal_provider is not None
        try:
            self.paypal_provider.suspend_subscription(
                provider_subscription_id,
                reason=str(reason or "Paused by user").strip() or "Paused by user",
            )
            details = self.paypal_provider.get_subscription_details(provider_subscription_id)
        except PayPalProviderError as exc:
            raise BillingServiceError(str(exc)) from exc

        self.store.apply_billing_webhook(
            event_type="billing.subscription.suspended",
            user_id=user_id,
            tier=str(subscription.get("tier", "free") or "free"),
            interval=str(subscription.get("interval", "monthly") or "monthly"),
            payment_provider="paypal",
            raw_payload={
                "event_type": "BILLING.SUBSCRIPTION.SUSPENDED",
                "resource": {
                    "id": details.subscription_id,
                    "status": details.status or "SUSPENDED",
                    "plan_id": details.plan_id,
                    "billing_info": {
                        "next_billing_time": details.next_billing_time,
                    },
                    "status_update_time": details.status_update_time,
                },
                "reason": str(reason or "Paused by user").strip() or "Paused by user",
            },
        )
        return self.store.get_subscription(user_id)

    def cancel_active_subscription(
        self,
        *,
        user_id: str,
        reason: str = "Cancelled by user",
    ) -> dict[str, Any]:
        subscription = self.store.get_subscription(user_id)
        provider_subscription_id = str(subscription.get("provider_subscription_id", "") or "").strip()
        if not provider_subscription_id:
            raise BillingServiceError("No active PayPal subscription is linked to this account.")
        if not self.paypal_configured:
            raise BillingServiceError("PayPal is not configured for live subscription actions.")

        assert self.paypal_provider is not None
        try:
            self.paypal_provider.cancel_subscription(
                provider_subscription_id,
                reason=str(reason or "Cancelled by user").strip() or "Cancelled by user",
            )
        except PayPalProviderError as exc:
            raise BillingServiceError(str(exc)) from exc

        self.store.apply_billing_webhook(
            event_type="billing.subscription.cancelled",
            user_id=user_id,
            tier=str(subscription.get("tier", "free") or "free"),
            interval=str(subscription.get("interval", "monthly") or "monthly"),
            payment_provider="paypal",
            raw_payload={
                "event_type": "BILLING.SUBSCRIPTION.CANCELLED",
                "resource": {
                    "id": provider_subscription_id,
                    "status": "CANCELLED",
                    "plan_id": str(subscription.get("provider_plan_id", "") or "").strip(),
                },
                "reason": str(reason or "Cancelled by user").strip() or "Cancelled by user",
            },
        )
        return self.store.get_subscription(user_id)

    def handle_paypal_webhook(
        self,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> BillingWebhookResult:
        event_type = str(payload.get("event_type", "") or "").strip()
        if not event_type:
            raise BillingServiceError("event_type is required.")

        self.store.prune_billing_webhook_memory(
            max_age_seconds=self.paypal_webhook_receipt_ttl_seconds
        )
        event_id = self._webhook_event_id(payload)
        idempotency_key = self._webhook_idempotency_key(payload=payload, event_id=event_id)

        verified = True
        transmission_id = ""
        replayed = False
        replay_key = ""
        if self._looks_like_paypal_webhook(headers):
            if not self.paypal_configured:
                raise BillingServiceError("PayPal webhook received but PayPal is not configured.")
            transmission_id = self._header(headers, "paypal-transmission-id")
            transmission_time = self._header(headers, "paypal-transmission-time")
            self._assert_transmission_fresh(transmission_time)
            replay_key = self._webhook_replay_key(transmission_id=transmission_id, event_id=event_id)
            if replay_key:
                replay_receipt = self.store.get_billing_webhook_replay(replay_key)
                if isinstance(replay_receipt, dict):
                    replayed = True
                    existing_receipt = self.store.get_billing_webhook_receipt(idempotency_key)
                    if isinstance(existing_receipt, dict):
                        return BillingWebhookResult(
                            user_id=str(existing_receipt.get("user_id", "") or "").strip(),
                            event_type=str(existing_receipt.get("event_type", "") or event_type).strip(),
                            verified=True,
                            checkout_session_id=str(
                                existing_receipt.get("checkout_session_id", "") or ""
                            ).strip(),
                            duplicate=True,
                            replayed=True,
                            webhook_event_id=event_id,
                            transmission_id=transmission_id,
                            idempotency_key=idempotency_key,
                        )
                    raise BillingServiceError("PayPal webhook replay detected.")
            assert self.paypal_provider is not None
            verification = self.paypal_provider.verify_webhook_signature(
                headers=headers,
                payload=payload,
            )
            if not verification.verified:
                raise BillingServiceError(
                    f"PayPal webhook signature verification failed: {verification.status or 'UNKNOWN'}"
                )

        existing_receipt = self.store.get_billing_webhook_receipt(idempotency_key)
        if isinstance(existing_receipt, dict):
            return BillingWebhookResult(
                user_id=str(existing_receipt.get("user_id", "") or "").strip(),
                event_type=str(existing_receipt.get("event_type", "") or event_type).strip(),
                verified=verified,
                checkout_session_id=str(existing_receipt.get("checkout_session_id", "") or "").strip(),
                duplicate=True,
                replayed=replayed,
                webhook_event_id=event_id,
                transmission_id=transmission_id,
                idempotency_key=idempotency_key,
            )

        checkout = self._resolve_checkout_from_payload(payload)
        user_id = str(payload.get("user_id", "") or "").strip()
        if not user_id and isinstance(checkout, dict):
            user_id = str(checkout.get("user_id", "") or "").strip()
        if not user_id:
            raise BillingServiceError("Unable to resolve the user for this billing event.")

        normalized_type = event_type.strip().lower()
        if isinstance(checkout, dict):
            subscription_id = self._provider_subscription_id_from_payload(payload)
            if subscription_id:
                checkout["provider_subscription_id"] = subscription_id
            plan_id = self._provider_plan_id_from_payload(payload)
            if plan_id:
                checkout["provider_plan_id"] = plan_id
            checkout["provider_status"] = self._provider_status_from_payload(payload)
            if normalized_type in self._completion_events():
                checkout["status"] = "completed"
                checkout["captured_at"] = self._now_iso()
            elif normalized_type in self._cancellation_events():
                checkout["status"] = "cancelled"
                checkout["cancelled_at"] = self._now_iso()
            elif normalized_type in self._approval_events():
                checkout["status"] = "approved"
            self.store.save()

        self.store.apply_billing_webhook(
            event_type=event_type,
            user_id=user_id,
            tier=self._tier_from_payload(payload, checkout),
            interval=self._interval_from_payload(payload, checkout),
            payment_provider="paypal",
            raw_payload=deepcopy(dict(payload)),
        )
        self.store.remember_billing_webhook_receipt(
            idempotency_key=idempotency_key,
            event_type=event_type,
            user_id=user_id,
            checkout_session_id=str((checkout or {}).get("session_id", "") or ""),
            event_id=event_id,
        )
        if replay_key:
            self.store.remember_billing_webhook_replay(
                replay_key=replay_key,
                transmission_id=transmission_id,
                event_id=event_id,
                idempotency_key=idempotency_key,
            )
        return BillingWebhookResult(
            user_id=user_id,
            event_type=event_type,
            verified=verified,
            checkout_session_id=str((checkout or {}).get("session_id", "") or ""),
            duplicate=False,
            replayed=replayed,
            webhook_event_id=event_id,
            transmission_id=transmission_id,
            idempotency_key=idempotency_key,
        )

    def _mark_checkout_completed(
        self,
        *,
        checkout: dict[str, Any],
        user_id: str,
        raw_payload: Mapping[str, Any] | None = None,
        event_type: str = "checkout.completed",
    ) -> dict[str, Any]:
        checkout["status"] = "completed"
        checkout["captured_at"] = self._now_iso()
        self.store.apply_billing_webhook(
            event_type=event_type,
            user_id=user_id,
            tier=str(checkout.get("tier", "standard") or "standard"),
            interval=str(checkout.get("interval", "monthly") or "monthly"),
            payment_provider="paypal",
            raw_payload=dict(raw_payload or {}),
        )
        self.store.save()
        return checkout

    def _require_checkout(self, *, session_id: str, user_id: str) -> dict[str, Any]:
        checkout = self.store.get_checkout_session(session_id)
        if not isinstance(checkout, dict):
            raise BillingServiceError("Checkout session not found.")
        owner = str(checkout.get("user_id", "") or "").strip()
        if owner != str(user_id or "").strip():
            raise BillingServiceError("Checkout session does not belong to this user.")
        return checkout

    def _resolve_checkout_from_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        session_id = str(payload.get("session_id", "") or "").strip()
        if session_id:
            checkout = self.store.get_checkout_session(session_id)
            if isinstance(checkout, dict):
                return checkout

        custom_id = self._custom_id_from_payload(payload)
        if custom_id:
            checkout = self.store.get_checkout_session(custom_id)
            if isinstance(checkout, dict):
                return checkout

        subscription_id = self._provider_subscription_id_from_payload(payload)
        if subscription_id:
            checkout = self.store.get_checkout_session_by_provider_subscription_id(subscription_id)
            if isinstance(checkout, dict):
                return checkout
        return None

    def _custom_id_from_payload(self, payload: Mapping[str, Any]) -> str:
        resource = payload.get("resource", {})
        if isinstance(resource, dict):
            direct = str(resource.get("custom_id", "") or "").strip()
            if direct:
                return direct
        return ""

    def _provider_subscription_id_from_payload(self, payload: Mapping[str, Any]) -> str:
        resource = payload.get("resource", {})
        if isinstance(resource, dict):
            resource_id = str(resource.get("id", "") or "").strip()
            event_type = str(payload.get("event_type", "") or "").strip().lower()
            if resource_id and event_type.startswith("billing.subscription."):
                return resource_id
            supplementary = resource.get("supplementary_data", {})
            if isinstance(supplementary, dict):
                related = supplementary.get("related_ids", {})
                if isinstance(related, dict):
                    subscription_id = str(related.get("subscription_id", "") or "").strip()
                    if subscription_id:
                        return subscription_id
            billing_agreement_id = str(resource.get("billing_agreement_id", "") or "").strip()
            if billing_agreement_id:
                return billing_agreement_id
        for key in ("provider_subscription_id", "subscription_id", "ba_token", "token"):
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def _provider_plan_id_from_payload(self, payload: Mapping[str, Any]) -> str:
        resource = payload.get("resource", {})
        if isinstance(resource, dict):
            plan_id = str(resource.get("plan_id", "") or "").strip()
            if plan_id:
                return plan_id
        return str(payload.get("provider_plan_id", "") or "").strip()

    def _provider_status_from_payload(self, payload: Mapping[str, Any]) -> str:
        resource = payload.get("resource", {})
        if isinstance(resource, dict):
            status = str(resource.get("status", "") or "").strip()
            if status:
                return status
        return str(payload.get("event_type", "") or "").strip().upper()

    def _tier_from_payload(
        self,
        payload: Mapping[str, Any],
        checkout: Mapping[str, Any] | None,
    ) -> str:
        tier = str(payload.get("tier", "") or "").strip().lower()
        if tier:
            return tier
        if isinstance(checkout, Mapping):
            tier = str(checkout.get("tier", "") or "").strip().lower()
            if tier:
                return tier
        plan_id = self._provider_plan_id_from_payload(payload)
        if plan_id:
            for (candidate_tier, _interval), candidate_plan_id in self.paypal_plan_ids.items():
                if candidate_plan_id == plan_id:
                    return candidate_tier
        return "standard"

    def _interval_from_payload(
        self,
        payload: Mapping[str, Any],
        checkout: Mapping[str, Any] | None,
    ) -> str:
        interval = str(payload.get("interval", "") or "").strip().lower()
        if interval:
            return interval
        if isinstance(checkout, Mapping):
            interval = str(checkout.get("interval", "") or "").strip().lower()
            if interval:
                return interval
        plan_id = self._provider_plan_id_from_payload(payload)
        if plan_id:
            for (_tier, candidate_interval), candidate_plan_id in self.paypal_plan_ids.items():
                if candidate_plan_id == plan_id:
                    return candidate_interval
        return "monthly"

    @staticmethod
    def _looks_like_paypal_webhook(headers: Mapping[str, str]) -> bool:
        for key in headers.keys():
            if str(key).strip().lower().startswith("paypal-"):
                return True
        return False

    @staticmethod
    def _approval_events() -> set[str]:
        return {
            "billing.subscription.created",
            "billing.subscription.updated",
        }

    @staticmethod
    def _completion_events() -> set[str]:
        return {
            "checkout.completed",
            "payment.succeeded",
            "subscription.renewed",
            "billing.subscription.activated",
            "billing.subscription.re-activated",
            "billing.subscription.renewed",
            "payment.sale.completed",
        }

    @staticmethod
    def _cancellation_events() -> set[str]:
        return {
            "subscription.cancelled",
            "subscription.expired",
            "billing.subscription.cancelled",
            "billing.subscription.expired",
            "billing.subscription.suspended",
        }

    def _apply_subscription_details(
        self,
        *,
        checkout: dict[str, Any],
        details: PayPalSubscriptionDetails,
    ) -> None:
        checkout["provider_subscription_id"] = details.subscription_id
        checkout["provider_plan_id"] = details.plan_id
        checkout["provider_status"] = details.status
        checkout["provider_environment"] = self.paypal_provider.environment if self.paypal_provider else ""
        checkout["provider_currency"] = self.paypal_provider.currency_code if self.paypal_provider else ""

    def _subscription_key(
        self,
        *,
        provider_subscription_id: str,
        provider_order_id: str,
        checkout: Mapping[str, Any],
    ) -> str:
        return (
            str(provider_subscription_id or "").strip()
            or str(provider_order_id or "").strip()
            or str(checkout.get("provider_subscription_id", "") or "").strip()
            or str(checkout.get("provider_order_id", "") or "").strip()
        )

    def _paypal_plan_id(self, *, tier: str, interval: str) -> str:
        return self.paypal_plan_ids.get(
            (str(tier or "").strip().lower(), str(interval or "").strip().lower()),
            "",
        )

    def _paypal_return_url(self, session_id: str) -> str:
        return self._join_url(
            "/billing/paypal/approve",
            {"session_id": session_id},
        )

    def _paypal_cancel_url(self, session_id: str) -> str:
        return self._join_url(
            "/billing/paypal/cancel",
            {"session_id": session_id},
        )

    def _join_url(self, path: str, query: Mapping[str, str]) -> str:
        base = self.app_base_url.rstrip("/")
        encoded = urlencode({key: value for key, value in query.items() if value})
        return f"{base}{path}{'?' + encoded if encoded else ''}"

    @staticmethod
    def _webhook_event_id(payload: Mapping[str, Any]) -> str:
        event_id = str(payload.get("id", "") or "").strip()
        if event_id:
            return event_id
        return str(payload.get("event_id", "") or "").strip()

    @staticmethod
    def _header(headers: Mapping[str, str], key: str) -> str:
        needle = str(key or "").strip().lower()
        for candidate_key, candidate_value in headers.items():
            if str(candidate_key or "").strip().lower() == needle:
                return str(candidate_value or "").strip()
        return ""

    @staticmethod
    def _webhook_payload_hash(payload: Mapping[str, Any]) -> str:
        try:
            encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
        except Exception:
            encoded = str(dict(payload)).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _webhook_idempotency_key(self, *, payload: Mapping[str, Any], event_id: str) -> str:
        if event_id:
            return f"paypal:event:{event_id}"
        return f"paypal:payload:{self._webhook_payload_hash(payload)}"

    @staticmethod
    def _webhook_replay_key(*, transmission_id: str, event_id: str) -> str:
        tx = str(transmission_id or "").strip()
        if not tx:
            return ""
        return f"paypal:tx:{tx}"

    def _assert_transmission_fresh(self, transmission_time: str) -> None:
        value = str(transmission_time or "").strip()
        if not value:
            raise BillingServiceError("Missing PayPal transmission timestamp.")
        try:
            transmitted_at = from_iso(value)
        except Exception as exc:
            raise BillingServiceError("Invalid PayPal transmission timestamp.") from exc
        age_seconds = abs((utcnow() - transmitted_at).total_seconds())
        if age_seconds > self.paypal_webhook_max_age_seconds:
            raise BillingServiceError("PayPal webhook transmission timestamp is outside the accepted window.")

    @staticmethod
    def _now_iso() -> str:
        return to_iso(utcnow().replace(microsecond=0))
