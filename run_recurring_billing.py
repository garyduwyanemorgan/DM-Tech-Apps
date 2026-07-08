#!/usr/bin/env python3
"""
Charge due Checkout.com subscription renewals.

Checkout.com has no Stripe-style automatic subscription billing — renewals
are merchant-initiated payments against the stored card source. This script
finds every org whose next_billing_at has passed and charges one billing
cycle via CheckoutComProvider.charge_recurring().

Schedule it to run daily (e.g. a Render Cron Job):

    python run_recurring_billing.py

Idempotent per run: a successful charge advances next_billing_at one month,
a declined charge marks the org past_due (retried on the next run). Orgs
billed by Stripe are never touched — Stripe bills those automatically.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("recurring_billing")


def main() -> int:
    from db.client import get_client
    from payments.checkout_provider import CheckoutComProvider

    provider = CheckoutComProvider()
    if not provider.is_configured():
        logger.error("Checkout.com is not configured — nothing to bill.")
        return 1

    client = get_client()
    if not client:
        logger.error("Database not available.")
        return 1

    now_iso = datetime.now(timezone.utc).isoformat()
    res = (
        client.table("organizations")
        .select("id, name, plan_name, next_billing_at")
        .eq("payment_provider", provider.name)
        .eq("subscription_status", "active")
        .lte("next_billing_at", now_iso)
        .execute()
    )
    due = res.data or []
    logger.info("Found %d organization(s) due for renewal.", len(due))

    failures = 0
    for org in due:
        org_id = org["id"]
        result = provider.charge_recurring(org_id)
        if result.get("charged"):
            logger.info("Charged org %s (%s): payment %s",
                        org_id, org.get("plan_name"), result.get("payment_id"))
        else:
            failures += 1
            logger.warning("Charge failed for org %s: %s", org_id, result.get("error"))

    logger.info("Done — %d charged, %d failed.", len(due) - failures, failures)
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
