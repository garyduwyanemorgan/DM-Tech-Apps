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

import os

from payments.base import PaymentProvider
from payments.config import read_secrets_block

DEFAULT_PROVIDER = "checkout"

_instances: dict[str, PaymentProvider] = {}


def provider_name() -> str:
    """Resolve the configured provider name (env var → secrets.toml → default)."""
    name = os.environ.get("PAYMENT_PROVIDER", "").strip().lower()
    if not name:
        block = read_secrets_block("payments")
        name = str(block.get("provider", "")).strip().lower()
    return name or DEFAULT_PROVIDER


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
