"""Stripe billing helpers — per-site SaaS enforcement.

All billing state is stored in the `organizations` table:
  site_limit              int     — max sites allowed on current plan
  plan_name               text    — starter / growth / professional / dev
  stripe_customer_id      text    — Stripe Customer ID (cus_...)
  stripe_subscription_id  text    — Stripe Subscription ID (sub_...)
"""
from __future__ import annotations

import os
import pathlib
import tomllib
from typing import Optional


# ── Plan catalogue ────────────────────────────────────────────────────────────

PLANS: dict[str, dict] = {
    "starter": {
        "name":       "Starter",
        "site_limit": 1,
        "price_usd":  199,
        "description": "1 lagoon site — ideal for single-property operators",
    },
    "growth": {
        "name":       "Growth",
        "site_limit": 5,
        "price_usd":  799,
        "description": "Up to 5 lagoon sites — small portfolio managers",
    },
    "professional": {
        "name":       "Professional",
        "site_limit": 15,
        "price_usd":  1999,
        "description": "Up to 15 lagoon sites — consultants and large portfolios",
    },
    "dev": {
        "name":       "Developer",
        "site_limit": 999,
        "price_usd":  0,
        "description": "Unlimited (development/testing)",
    },
}


# ── Secrets ───────────────────────────────────────────────────────────────────

def _stripe_secrets() -> dict:
    """Read Stripe keys from secrets.toml or env vars."""
    try:
        toml_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        block = data.get("stripe", {})
        if block.get("secret_key"):
            return block
    except Exception:
        pass
    return {
        "secret_key":        os.environ.get("STRIPE_SECRET_KEY", ""),
        "webhook_secret":    os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
        "price_starter":     os.environ.get("STRIPE_PRICE_STARTER", ""),
        "price_growth":      os.environ.get("STRIPE_PRICE_GROWTH", ""),
        "price_professional":os.environ.get("STRIPE_PRICE_PROFESSIONAL", ""),
    }


def is_configured() -> bool:
    return bool(_stripe_secrets().get("secret_key"))


def _stripe():
    import stripe as _stripe_lib
    secrets = _stripe_secrets()
    _stripe_lib.api_key = secrets["secret_key"]
    return _stripe_lib


def price_id_for_plan(plan_key: str) -> Optional[str]:
    secrets = _stripe_secrets()
    return secrets.get(f"price_{plan_key}") or None


def plan_key_for_price_id(price_id: str) -> Optional[str]:
    """Reverse-map a Stripe price ID back to a plan key. Used for portal-driven plan changes
    where Stripe does not update subscription metadata."""
    secrets = _stripe_secrets()
    for key in PLANS:
        if secrets.get(f"price_{key}") == price_id:
            return key
    return None


def webhook_secret() -> str:
    return _stripe_secrets().get("webhook_secret", "")


# ── Org helpers ───────────────────────────────────────────────────────────────

def get_org_billing(org_id: str) -> dict:
    """Fetch billing fields from the organizations table."""
    from db.client import get_client
    client = get_client()
    if not client:
        return {"site_limit": 1, "plan_name": "starter"}
    try:
        res = client.table("organizations").select(
            "site_limit, plan_name, stripe_customer_id, stripe_subscription_id"
        ).eq("id", org_id).single().execute()
        data = res.data or {}
        # Coalesce NULLs so downstream arithmetic on site_limit never sees None
        # (legacy orgs created before billing defaults were enforced).
        return {
            "site_limit": data.get("site_limit") or 1,
            "plan_name": data.get("plan_name") or "starter",
            "stripe_customer_id": data.get("stripe_customer_id"),
            "stripe_subscription_id": data.get("stripe_subscription_id"),
        }
    except Exception:
        return {"site_limit": 1, "plan_name": "starter"}


def update_org_billing(org_id: str, **fields) -> bool:
    """Write billing fields back to the organizations table."""
    from db.client import get_client
    client = get_client()
    if not client:
        return False
    try:
        client.table("organizations").update(fields).eq("id", org_id).execute()
        return True
    except Exception:
        return False


def count_sites(org_id: str) -> int:
    from db.client import get_client
    client = get_client()
    if not client:
        return 0
    try:
        res = client.table("sites").select("id", count="exact").eq("organization_id", org_id).execute()
        return res.count or 0
    except Exception:
        return 0


# ── Stripe operations ─────────────────────────────────────────────────────────

def get_or_create_customer(org_id: str, email: str, org_name: str = "") -> Optional[str]:
    """Return existing Stripe customer ID or create one."""
    billing = get_org_billing(org_id)
    existing_cust = billing.get("stripe_customer_id")
    if existing_cust:
        return existing_cust
    s = _stripe()
    cust = s.Customer.create(
        email=email,
        name=org_name or email,
        metadata={"organization_id": org_id},
    )
    update_org_billing(org_id, stripe_customer_id=cust.id)
    return cust.id


def create_checkout_session(
    org_id: str,
    plan_key: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
) -> Optional[str]:
    """Create a Stripe Checkout Session. Returns the session URL."""
    price = price_id_for_plan(plan_key)
    if not price:
        return None
    s = _stripe()
    customer_id = get_or_create_customer(org_id, user_email)
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


def create_portal_session(org_id: str, return_url: str) -> Optional[str]:
    """Create a Stripe Customer Portal session. Returns the portal URL."""
    billing = get_org_billing(org_id)
    customer_id = billing.get("stripe_customer_id")
    if not customer_id:
        return None
    s = _stripe()
    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify and process a Stripe webhook event. Returns {"handled": bool, "event_type": str}."""
    s = _stripe()
    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret())
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
                    plan_key = plan_key_for_price_id(price_id)
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
