"""PaymentProvider — the interface every payment provider must implement.

The rest of the application (billing.py facade, /billing/* endpoints, the
frontend) talks only to this interface. Nothing outside payments/ may
reference a concrete provider or its SDK.

Capabilities covered:
  - customer creation            get_or_create_customer()
  - subscription creation        create_checkout_session()
  - recurring billing            charge_recurring()  (no-op for providers
                                 that bill automatically, e.g. Stripe)
  - webhook handling             handle_webhook()
  - subscription cancellation    cancel_subscription()
  - payment status updates       get_subscription_status() + webhook events
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class PaymentProvider(ABC):
    """Abstract payment provider. All org billing state lives in the
    `organizations` table; providers read/write it via billing helpers."""

    #: short machine name, e.g. "stripe" / "checkout"
    name: str = "base"

    # ── configuration ─────────────────────────────────────────────────────

    @abstractmethod
    def is_configured(self) -> bool:
        """True when API credentials are present for this provider."""

    @property
    def supports_portal(self) -> bool:
        """True if the provider offers a hosted self-service billing portal."""
        return False

    # ── customers ─────────────────────────────────────────────────────────

    @abstractmethod
    def get_or_create_customer(self, org_id: str, email: str, org_name: str = "") -> Optional[str]:
        """Return the provider customer ID for an org, creating it if needed."""

    # ── subscriptions ─────────────────────────────────────────────────────

    @abstractmethod
    def create_checkout_session(
        self,
        org_id: str,
        plan_key: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
    ) -> Optional[str]:
        """Start a subscription purchase. Returns a hosted payment page URL
        to redirect the user to, or None if the plan cannot be purchased."""

    @abstractmethod
    def cancel_subscription(self, org_id: str) -> bool:
        """Cancel the org's active subscription and downgrade its plan."""

    @abstractmethod
    def get_subscription_status(self, org_id: str) -> dict:
        """Current payment/subscription status for an org.
        Returns at least {"provider": str, "status": str}."""

    def create_portal_session(self, org_id: str, return_url: str) -> Optional[str]:
        """Hosted billing-portal URL, or None if unsupported (see supports_portal)."""
        return None

    # ── recurring billing ─────────────────────────────────────────────────

    def charge_recurring(self, org_id: str) -> dict:
        """Charge the next billing cycle for providers that require
        merchant-initiated recurring payments. Providers that bill
        automatically (Stripe subscriptions) keep this default no-op.
        Returns {"charged": bool, ...}."""
        return {"charged": False, "reason": f"{self.name} bills subscriptions automatically."}

    # ── webhooks ──────────────────────────────────────────────────────────

    @abstractmethod
    def handle_webhook(self, payload: bytes, headers: dict) -> dict:
        """Verify and process a webhook request. `headers` is the full
        (case-insensitive) request header mapping — each provider extracts
        its own signature header. Returns {"handled": bool, "event_type": str}
        or {"handled": False, "error": str} on verification failure."""
