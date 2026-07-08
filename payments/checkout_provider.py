"""Checkout.com implementation of PaymentProvider (active default).

Credentials — [checkout] block in .streamlit/secrets.toml or env vars:

    [checkout]
    secret_key      = "sk_..."        # sk_sbox_... routes to the sandbox API
    webhook_secret  = "..."           # HMAC key used to sign webhook payloads
    billing_country = "AE"            # ISO country for hosted payment pages

    CHECKOUT_SECRET_KEY / CHECKOUT_WEBHOOK_SECRET / CHECKOUT_BILLING_COUNTRY

How subscriptions work here (Checkout.com has no Stripe-style subscription
object, so the subscription lifecycle lives in the organizations table):

  1. create_checkout_session() → Hosted Payments Page for the first payment
     of a recurring series (payment_type "Recurring", card stored for
     future merchant-initiated use).
  2. The payment_approved webhook activates the plan and stores the payment
     source ID (payment_source_id) + first payment ID
     (payment_subscription_id, the anchor for the recurring series) and
     sets next_billing_at one month out.
  3. charge_recurring() — invoked by run_recurring_billing.py on a daily
     schedule — charges the stored source for each org whose
     next_billing_at has passed, advancing next_billing_at on success and
     marking the org past_due on decline.
  4. cancel_subscription() clears the stored source and downgrades the org.

Webhook signature: `cko-signature` header = hex HMAC-SHA256 of the raw
payload keyed with webhook_secret.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from payments.base import PaymentProvider
from payments.config import read_secrets_block

logger = logging.getLogger(__name__)

API_LIVE = "https://api.checkout.com"
API_SANDBOX = "https://api.sandbox.checkout.com"

# Events the webhook endpoint (create_checkout_webhook.py) subscribes to
WEBHOOK_EVENTS = ["payment_approved", "payment_captured", "payment_declined", "payment_refunded"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _add_month(dt: datetime) -> datetime:
    """Same day next month, clamped to month length (Jan 31 → Feb 28)."""
    year, month = (dt.year + 1, 1) if dt.month == 12 else (dt.year, dt.month + 1)
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class CheckoutComProvider(PaymentProvider):

    name = "checkout"

    # ── secrets / HTTP plumbing ───────────────────────────────────────────

    def _secrets(self) -> dict:
        block = read_secrets_block("checkout")
        if block.get("secret_key"):
            return block
        return {
            "secret_key":      os.environ.get("CHECKOUT_SECRET_KEY", ""),
            "webhook_secret":  os.environ.get("CHECKOUT_WEBHOOK_SECRET", ""),
            "billing_country": os.environ.get("CHECKOUT_BILLING_COUNTRY", "AE"),
        }

    def is_configured(self) -> bool:
        return bool(self._secrets().get("secret_key"))

    def _base_url(self) -> str:
        key = self._secrets().get("secret_key", "")
        return API_SANDBOX if "sbox" in key else API_LIVE

    def _billing_country(self) -> str:
        return self._secrets().get("billing_country") or "AE"

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> tuple[int, dict]:
        """Call the Checkout.com API. Returns (status_code, response_json)."""
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "The 'httpx' package is not installed. Install it with "
                "'pip install httpx' (see requirements.txt)."
            ) from exc
        headers = {
            "Authorization": f"Bearer {self._secrets()['secret_key']}",
            "Content-Type": "application/json",
        }
        resp = httpx.request(method, f"{self._base_url()}{path}", json=body, headers=headers, timeout=30.0)
        try:
            data: dict[str, Any] = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        return resp.status_code, data

    # ── customers ─────────────────────────────────────────────────────────

    def get_or_create_customer(self, org_id: str, email: str, org_name: str = "") -> Optional[str]:
        """Return existing Checkout.com customer ID for the org or create one."""
        from billing import get_org_billing, update_org_billing
        billing = get_org_billing(org_id)
        existing = billing.get("payment_customer_id")
        if existing and billing.get("payment_provider") == self.name:
            return existing
        status, data = self._request("POST", "/customers", {
            "email": email,
            "name": org_name or email,
            "metadata": {"organization_id": org_id},
        })
        if status == 201 and data.get("id"):
            customer_id = data["id"]
        elif status == 409:
            # Customer already exists for this email — look it up
            status, data = self._request("GET", f"/customers/{email}")
            if status != 200 or not data.get("id"):
                logger.error("Checkout.com customer lookup failed for %s: HTTP %s", email, status)
                return None
            customer_id = data["id"]
        else:
            logger.error("Checkout.com customer creation failed: HTTP %s %s", status, data)
            return None
        update_org_billing(org_id, payment_provider=self.name, payment_customer_id=customer_id)
        return customer_id

    # ── subscriptions ─────────────────────────────────────────────────────

    def create_checkout_session(
        self,
        org_id: str,
        plan_key: str,
        user_email: str,
        success_url: str,
        cancel_url: str,
    ) -> Optional[str]:
        """Create a Hosted Payments Page for the first payment of a recurring
        series. Returns the redirect URL."""
        from billing import PLANS
        plan = PLANS.get(plan_key)
        if not plan or not plan["price_usd"]:
            return None
        self.get_or_create_customer(org_id, user_email)
        status, data = self._request("POST", "/hosted-payments", {
            "amount": plan["price_usd"] * 100,  # minor units (cents)
            "currency": "USD",
            "payment_type": "Recurring",
            "store_for_future_use": True,
            "reference": f"{org_id}:{plan_key}",
            "description": f"Dubai Lagoons — {plan['name']} plan (monthly)",
            "customer": {"email": user_email},
            "metadata": {"organization_id": org_id, "plan": plan_key},
            "billing": {"address": {"country": self._billing_country()}},
            "success_url": success_url,
            "cancel_url": cancel_url,
            "failure_url": cancel_url,
        })
        if status != 201:
            logger.error("Checkout.com hosted payment creation failed: HTTP %s %s", status, data)
            return None
        return (data.get("_links", {}).get("redirect", {}) or {}).get("href")

    def cancel_subscription(self, org_id: str) -> bool:
        """Stop the recurring series and downgrade the org to starter.
        The series is merchant-initiated, so clearing the stored source is
        sufficient — no remote object to cancel."""
        from billing import PLANS, get_org_billing, update_org_billing
        billing = get_org_billing(org_id)
        if not billing.get("payment_subscription_id"):
            return False
        return update_org_billing(
            org_id,
            payment_subscription_id=None,
            payment_source_id=None,
            subscription_status="cancelled",
            next_billing_at=None,
            plan_name="starter",
            site_limit=PLANS["starter"]["site_limit"],
        )

    def get_subscription_status(self, org_id: str) -> dict:
        from billing import get_org_billing
        billing = get_org_billing(org_id)
        sub_id = billing.get("payment_subscription_id")
        if not sub_id:
            return {"provider": self.name, "status": billing.get("subscription_status") or "none"}
        return {
            "provider": self.name,
            "status": billing.get("subscription_status") or "active",
            "subscription_id": sub_id,
            "next_billing_at": billing.get("next_billing_at"),
        }

    # ── recurring billing ─────────────────────────────────────────────────

    def charge_recurring(self, org_id: str) -> dict:
        """Charge one billing cycle against the stored payment source.
        Called by run_recurring_billing.py for orgs whose next_billing_at
        has passed."""
        from billing import PLANS, get_org_billing, update_org_billing
        billing = get_org_billing(org_id)
        source_id = billing.get("payment_source_id")
        plan_key = billing.get("plan_name", "starter")
        plan = PLANS.get(plan_key)
        if not source_id:
            return {"charged": False, "error": "No stored payment source for this organization."}
        if not plan or not plan["price_usd"]:
            return {"charged": False, "error": f"Plan '{plan_key}' has no recurring charge."}
        status, data = self._request("POST", "/payments", {
            "source": {"type": "id", "id": source_id},
            "amount": plan["price_usd"] * 100,
            "currency": "USD",
            "payment_type": "Recurring",
            "merchant_initiated": True,
            "previous_payment_id": billing.get("payment_subscription_id"),
            "reference": f"{org_id}:{plan_key}:renewal",
            "metadata": {"organization_id": org_id, "plan": plan_key, "recurring": "true"},
        })
        if status in (201, 202) and data.get("approved"):
            update_org_billing(
                org_id,
                subscription_status="active",
                next_billing_at=_add_month(_utcnow()).isoformat(),
            )
            return {"charged": True, "payment_id": data.get("id")}
        logger.warning("Checkout.com recurring charge declined for org %s: HTTP %s %s",
                       org_id, status, data.get("response_summary"))
        update_org_billing(org_id, subscription_status="past_due")
        return {"charged": False, "error": data.get("response_summary") or f"HTTP {status}"}

    # ── webhooks ──────────────────────────────────────────────────────────

    def _verify_signature(self, payload: bytes, headers: dict) -> bool:
        secret = self._secrets().get("webhook_secret", "")
        if not secret:
            return False
        sig = {k.lower(): v for k, v in headers.items()}.get("cko-signature", "")
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return bool(sig) and hmac.compare_digest(expected.lower(), sig.lower())

    def handle_webhook(self, payload: bytes, headers: dict) -> dict:
        """Verify and process a Checkout.com webhook event.
        Returns {"handled": bool, "event_type": str}."""
        from billing import PLANS, update_org_billing
        if not self._verify_signature(payload, headers):
            return {"handled": False, "error": "Invalid signature"}
        try:
            event = json.loads(payload)
        except ValueError:
            return {"handled": False, "error": "Invalid payload"}

        et = event.get("type", "")
        data = event.get("data", {}) or {}
        meta = data.get("metadata", {}) or {}
        org_id = meta.get("organization_id")
        if not org_id:
            # Not a payment we initiated — acknowledge and ignore
            return {"handled": True, "event_type": et}
        is_renewal = meta.get("recurring") == "true"

        if et in ("payment_approved", "payment_captured"):
            if is_renewal:
                # charge_recurring() already advanced next_billing_at; this
                # confirms the payment status.
                update_org_billing(org_id, subscription_status="active")
            else:
                # First payment of the series — activate the plan and store
                # the card source for future merchant-initiated charges.
                plan_key = meta.get("plan", "starter")
                plan = PLANS.get(plan_key, PLANS["starter"])
                fields: dict = {
                    "payment_provider": self.name,
                    "payment_subscription_id": data.get("id"),
                    "subscription_status": "active",
                    "plan_name": plan_key,
                    "site_limit": plan["site_limit"],
                    "next_billing_at": _add_month(_utcnow()).isoformat(),
                }
                source_id = (data.get("source") or {}).get("id")
                if source_id:
                    fields["payment_source_id"] = source_id
                customer_id = (data.get("customer") or {}).get("id")
                if customer_id:
                    fields["payment_customer_id"] = customer_id
                update_org_billing(org_id, **fields)

        elif et == "payment_declined":
            if is_renewal:
                update_org_billing(org_id, subscription_status="past_due")
            # Declined first payments need no action — the plan was never activated.

        elif et == "payment_refunded":
            update_org_billing(org_id, subscription_status="refunded")

        return {"handled": True, "event_type": et}
