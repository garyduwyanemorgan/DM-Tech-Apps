"""Billing facade — per-site SaaS enforcement, provider-agnostic.

Plan catalogue and organization billing state live here; all payment
operations are delegated to the active PaymentProvider (see payments/).
The active provider is chosen by configuration (PAYMENT_PROVIDER env var or
[payments] provider in secrets.toml) — Checkout.com by default, Stripe
available by switching config. Nothing outside payments/ touches a provider
SDK.

Billing state is stored in the `organizations` table:
  site_limit               int    — max sites allowed on current plan
  plan_name                text   — starter / growth / professional / dev
  payment_provider         text   — provider that owns the subscription
  payment_customer_id      text   — provider customer ID
  payment_subscription_id  text   — provider subscription / series anchor ID
  payment_source_id        text   — stored payment instrument (recurring)
  subscription_status      text   — active / past_due / cancelled / refunded
  next_billing_at          timestamptz — next merchant-initiated charge
  stripe_customer_id       text   — legacy Stripe columns (kept intact)
  stripe_subscription_id   text
"""
from __future__ import annotations

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


# ── Active payment provider ───────────────────────────────────────────────────

def get_provider():
    """Return the configured PaymentProvider instance."""
    from payments import get_provider as _get_provider
    return _get_provider()


def provider_name() -> str:
    from payments import provider_name as _provider_name
    return _provider_name()


def is_configured() -> bool:
    return get_provider().is_configured()


def supports_portal() -> bool:
    return get_provider().supports_portal


# ── Org helpers ───────────────────────────────────────────────────────────────

_BILLING_COLUMNS = (
    "site_limit, plan_name, stripe_customer_id, stripe_subscription_id, "
    "payment_provider, payment_customer_id, payment_subscription_id, "
    "payment_source_id, subscription_status, next_billing_at"
)
# Pre-002-migration column set — fallback so orgs keep working until
# db/migrations/002_payment_provider.sql has been applied.
_LEGACY_COLUMNS = "site_limit, plan_name, stripe_customer_id, stripe_subscription_id"


def get_org_billing(org_id: str) -> dict:
    """Fetch billing fields from the organizations table."""
    from db.client import get_client
    client = get_client()
    if not client:
        return {"site_limit": 1, "plan_name": "starter"}
    data: dict = {}
    for columns in (_BILLING_COLUMNS, _LEGACY_COLUMNS):
        try:
            res = client.table("organizations").select(columns).eq("id", org_id).single().execute()
            data = res.data or {}
            break
        except Exception:
            continue
    if not data:
        return {"site_limit": 1, "plan_name": "starter"}
    # Coalesce NULLs so downstream arithmetic on site_limit never sees None
    # (legacy orgs created before billing defaults were enforced).
    return {
        "site_limit": data.get("site_limit") or 1,
        "plan_name": data.get("plan_name") or "starter",
        "stripe_customer_id": data.get("stripe_customer_id"),
        "stripe_subscription_id": data.get("stripe_subscription_id"),
        "payment_provider": data.get("payment_provider"),
        "payment_customer_id": data.get("payment_customer_id"),
        "payment_subscription_id": data.get("payment_subscription_id"),
        "payment_source_id": data.get("payment_source_id"),
        "subscription_status": data.get("subscription_status"),
        "next_billing_at": data.get("next_billing_at"),
    }


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


def has_subscription(billing: dict) -> bool:
    """True if the org has an active subscription with any provider."""
    return bool(billing.get("payment_subscription_id") or billing.get("stripe_subscription_id"))


# ── Payment operations (delegated to the active provider) ────────────────────

def get_or_create_customer(org_id: str, email: str, org_name: str = "") -> Optional[str]:
    """Return the provider customer ID for an org, creating it if needed."""
    return get_provider().get_or_create_customer(org_id, email, org_name)


def create_checkout_session(
    org_id: str,
    plan_key: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
) -> Optional[str]:
    """Start a subscription purchase. Returns the hosted payment page URL."""
    return get_provider().create_checkout_session(
        org_id=org_id,
        plan_key=plan_key,
        user_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
    )


def create_portal_session(org_id: str, return_url: str) -> Optional[str]:
    """Hosted billing-portal URL, or None if the provider has no portal."""
    return get_provider().create_portal_session(org_id, return_url)


def _owning_provider(org_id: str):
    """Provider that owns the org's existing subscription — an org that
    subscribed via Stripe must still be cancelled/queried through Stripe even
    while another provider is active for new checkouts. Falls back to the
    active provider for orgs with no recorded provider."""
    from payments import get_provider as _get_provider
    billing = get_org_billing(org_id)
    owner = billing.get("payment_provider")
    if not owner and billing.get("stripe_subscription_id"):
        owner = "stripe"
    try:
        return _get_provider(owner) if owner else get_provider()
    except ValueError:
        return get_provider()


def cancel_subscription(org_id: str) -> bool:
    """Cancel the org's subscription and downgrade its plan."""
    return _owning_provider(org_id).cancel_subscription(org_id)


def get_subscription_status(org_id: str) -> dict:
    """Current payment/subscription status for an org."""
    return _owning_provider(org_id).get_subscription_status(org_id)


def charge_recurring(org_id: str) -> dict:
    """Charge the next billing cycle (providers with merchant-initiated billing)."""
    return get_provider().charge_recurring(org_id)


def handle_webhook(payload: bytes, headers: dict) -> dict:
    """Verify and process a payment webhook. `headers` is the full request
    header mapping — the provider extracts its own signature header."""
    return get_provider().handle_webhook(payload, headers)
