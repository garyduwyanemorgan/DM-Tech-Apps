"""Payment provider abstraction layer.

The active provider is selected by configuration — no code changes needed
to switch:

  1. ``PAYMENT_PROVIDER`` environment variable  (e.g. PAYMENT_PROVIDER=stripe)
  2. ``[payments] provider = "..."`` in .streamlit/secrets.toml
  3. Default: "checkout" (Checkout.com)

Available providers:
  checkout — Checkout.com (active default)
  stripe   — Stripe (kept intact; re-enable via configuration above)
"""
from __future__ import annotations

from core.config import secret
from payments.base import PaymentProvider

DEFAULT_PROVIDER = "checkout"

_instances: dict[str, PaymentProvider] = {}


def provider_name() -> str:
    """Resolve the configured provider name (env var → .env → secrets.toml → default)."""
    return secret("payments", "provider").lower() or DEFAULT_PROVIDER


def get_provider(name: str | None = None) -> PaymentProvider:
    """Return the active (or explicitly named) payment provider instance."""
    key = (name or provider_name()).lower()
    if key not in _instances:
        if key == "stripe":
            from payments.stripe_provider import StripeProvider
            _instances[key] = StripeProvider()
        elif key == "checkout":
            from payments.checkout_provider import CheckoutComProvider
            _instances[key] = CheckoutComProvider()
        else:
            raise ValueError(
                f"Unknown payment provider '{key}'. "
                "Valid values: 'checkout', 'stripe'. "
                "Set PAYMENT_PROVIDER or [payments] provider in secrets.toml."
            )
    return _instances[key]
