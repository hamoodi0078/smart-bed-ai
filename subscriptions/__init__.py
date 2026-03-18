"""Lazy exports for subscription gate and billing helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "BillingService",
    "BillingServiceError",
    "PayPalProvider",
    "PayPalProviderError",
    "SubscriptionGate",
]


def __getattr__(name: str) -> Any:
    if name == "SubscriptionGate":
        from .gate import SubscriptionGate

        globals()[name] = SubscriptionGate
        return SubscriptionGate
    if name in {"BillingService", "BillingServiceError"}:
        from .billing import BillingService, BillingServiceError

        globals()["BillingService"] = BillingService
        globals()["BillingServiceError"] = BillingServiceError
        return globals()[name]
    if name in {"PayPalProvider", "PayPalProviderError"}:
        from .paypal_provider import PayPalProvider, PayPalProviderError

        globals()["PayPalProvider"] = PayPalProvider
        globals()["PayPalProviderError"] = PayPalProviderError
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
