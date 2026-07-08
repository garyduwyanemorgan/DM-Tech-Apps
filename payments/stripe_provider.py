"""Stripe implementation of PaymentProvider.

DISABLED BY DEFAULT — the platform now runs on Checkout.com. This
implementation is kept intact and can be re-enabled with no code changes by
setting either:

    PAYMENT_PROVIDER=stripe                      (environment variable)
    [payments] provider = "stripe"               (.streamlit/secrets.toml)

Credentials come from the [stripe] block in secrets.toml or STRIPE_* env
vars, exactly as before. Stripe subscriptions bill automatically, so the
base-class charge_recurring() no-op applies.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from payments.base import PaymentProvider
from payments.config import read_secrets_block

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):

    name = "stripe"

    # ── secrets ───────────────────────────────────────────────────────────

    def _secrets(self) -> dict:
        """Read Stripe keys from secrets.toml or env vars."""
        block = read_secrets_block("stripe")
        if block.get("secret_key"):
            return block
        return {
            "secret_key":         os.environ.get("STRIPE_SECRET_KEY", ""),
            "webhook_secret":     os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            "price_starter":      os.environ.get("STRIPE_PRICE_STARTER", ""),
            "price_growth":       os.environ.get("STRIPE_PRICE_GROWTH", ""),
            "price_professional": os.environ.get("STRIPE_PRICE_PROFESSIONAL", ""),
        }

    def is_configured(self) -> bool:
        return bool(self._secrets().get("secret_key"))

    @property
    def supports_portal(self) -> bool:
        return True

    def _stripe(self):
        try:
            import stripe as _stripe_lib
        except ImportError as exc:
            raise RuntimeError(
                "The 'stripe' package is not installed. Install it with "
                "'pip install stripe' (see requirements.txt)."
            ) from exc
        _stripe_lib.api_key = self._secrets()["secret_key"]
        return _stripe_lib

    def price_id_for_plan(self, plan_key: str) -> Optional[str]:
        return self._secrets().get(f"price_{plan_key}") or None

    def plan_key_for_price_id(self, price_id: str) -> Optional[str]:
        """Reverse-map a Stripe price ID back to a plan key. Used for portal-driven
        plan changes where Stripe does not update subscription metadata."""
        from billing import PLANS
        secrets = self._secrets()
        for key in PLANS:
            if secrets.get(f"price_{key}") == price_id:
                return key
        return None

    def webhook_secret(self) -> str:
        return self._secrets().get("webhook_secret", "")

    # ── customers ─────────────────────────────────────────────────────────

    def get_or_create_customer(self, org_id: str, email: str, org_name: str = "") -> Optional[str]:
        """Return existing Stripe customer ID or create one."""
        from billing import get_org_billing, update_org_billing
        billing = get_org_billing(org_id)
        existing_cust = billing.get("stripe_customer_id")
        if existing_cust:
            return existing_cust
        s = self._stripe()
        cust = s.Customer.create(
            email=email,
            name=org_name or email,
            metadata={"organization_id": org_id},
        )
        update_org_billing(org_id, stripe_customer_id=cust.id)
        return cust.id

    # ── subscriptions ─────────────────────────────────────────────────────

    def create_checkout_session(
        self,
        org_id: str,
        plan_key: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
    ) -> Optional[str]:
        """Create a Stripe Checkout Session. Returns the session URL."""
        price = self.price_id_for_plan(plan_key)
        if not price:
            return None
        s = self._stripe()
        customer_id = self.get_or_create_customer(org_id, user_email)
        session = s.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            subscription_data={"metadata": {"organization_id": org_id, "plan": plan_key}},
            metadata={"organization_id": org_id, "plan": plan_key},
            allow_promotion_codes=True,
        )
        return session.url

    def create_portal_session(self, org_id: str, return_url: str) -> Optional[str]:
        """Create a Stripe Customer Portal session. Returns the portal URL."""
        from billing import get_org_billing
        billing = get_org_billing(org_id)
        customer_id = billing.get("stripe_customer_id")
        if not customer_id:
            return None
        s = self._stripe()
        session = s.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def cancel_subscription(self, org_id: str) -> bool:
        """Cancel the org's Stripe subscription immediately and downgrade to starter."""
        from billing import PLANS, get_org_billing, update_org_billing
        billing = get_org_billing(org_id)
        sub_id = billing.get("stripe_subscription_id")
        if not sub_id:
            return False
        s = self._stripe()
        try:
            s.Subscription.cancel(sub_id)
        except Exception as exc:
            logger.error("Stripe subscription cancel failed for org %s: %s", org_id, exc)
            return False
        # The customer.subscription.deleted webhook also downgrades, but do it
        # eagerly so the UI reflects the cancellation immediately.
        update_org_billing(
            org_id,
            stripe_subscription_id=None,
            plan_name="starter",
            site_limit=PLANS["starter"]["site_limit"],
        )
        return True

    def get_subscription_status(self, org_id: str) -> dict:
        from billing import get_org_billing
        billing = get_org_billing(org_id)
        sub_id = billing.get("stripe_subscription_id")
        if not sub_id:
            return {"provider": self.name, "status": "none"}
        try:
            s = self._stripe()
            sub = s.Subscription.retrieve(sub_id)
            return {
                "provider": self.name,
                "status": sub.get("status", "unknown"),
                "subscription_id": sub_id,
                "current_period_end": sub.get("current_period_end"),
            }
        except Exception as exc:
            logger.error("Stripe subscription lookup failed for org %s: %s", org_id, exc)
            return {"provider": self.name, "status": "unknown", "subscription_id": sub_id}

    # ── webhooks ──────────────────────────────────────────────────────────

    def handle_webhook(self, payload: bytes, headers: dict) -> dict:
        """Verify and process a Stripe webhook event. Returns {"handled": bool, "event_type": str}."""
        from billing import PLANS, update_org_billing
        sig_header = {k.lower(): v for k, v in headers.items()}.get("stripe-signature", "")
        s = self._stripe()
        try:
            event = s.Webhook.construct_event(payload, sig_header, self.webhook_secret())
        except s.error.SignatureVerificationError:
            return {"handled": False, "error": "Invalid signature"}

        et = event["type"]

        if et in ("customer.subscription.created", "customer.subscription.updated"):
            sub = event["data"]["object"]
            org_id = sub.get("metadata", {}).get("organization_id")
            if org_id:
                # Derive plan from the active price ID — metadata is stale after portal plan changes.
                plan_key = None
                items = sub.get("items", {}).get("data", [])
                if items:
                    price_id = items[0].get("price", {}).get("id")
                    if price_id:
                        plan_key = self.plan_key_for_price_id(price_id)
                # Fall back to metadata for subscriptions created before price-ID mapping was in place.
                if not plan_key:
                    plan_key = sub.get("metadata", {}).get("plan", "starter")
                plan = PLANS.get(plan_key, PLANS["starter"])
                update_org_billing(
                    org_id,
                    stripe_subscription_id=sub["id"],
                    plan_name=plan_key,
                    site_limit=plan["site_limit"],
                )

        elif et == "customer.subscription.deleted":
            sub = event["data"]["object"]
            org_id = sub.get("metadata", {}).get("organization_id")
            if org_id:
                # Downgrade to starter on cancellation
                update_org_billing(
                    org_id,
                    stripe_subscription_id=None,
                    plan_name="starter",
                    site_limit=PLANS["starter"]["site_limit"],
                )

        elif et == "checkout.session.completed":
            session = event["data"]["object"]
            org_id = session.get("metadata", {}).get("organization_id")
            plan_key = session.get("metadata", {}).get("plan", "starter")
            customer_id = session.get("customer")
            sub_id = session.get("subscription")
            if org_id:
                plan = PLANS.get(plan_key, PLANS["starter"])
                update_org_billing(
                    org_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=sub_id,
                    plan_name=plan_key,
                    site_limit=plan["site_limit"],
                )

        return {"handled": True, "event_type": et}
