"""Billing facade — base platform fee plus per-module add-ons, provider-agnostic.

§8 decision 4 / §4.5: THE UNIT OF SALE IS A GUIDELINE MODULE, NOT A SITE. A
client ticks the reports they need and the charge rises with the number ticked.
The site-count tiers this module used to price on are gone: sites, users and the
platform itself are covered by one base platform fee, and everything above that
is `organization_entitlements` joined to `guideline_modules` (023).

`payments/` is deliberately untouched by that change — the provider abstraction
does not care what is being charged for. The active provider is chosen by
configuration (PAYMENT_PROVIDER env var or [payments] provider in secrets.toml).
Nothing outside payments/ touches a provider SDK.

WHAT IS CHARGED (compute_invoice / price_period below)
------------------------------------------------------
  base platform fee                          — always, one per organisation
+ one add-on per ACTIVE entitled module      — price_agreed, else list price

RULES, AND THE JUDGEMENT CALLS BEHIND THEM. Each of these is a decision §4.5
does not make explicitly; they are stated here rather than buried in the code so
that changing the commercial model means changing one documented rule.

  * ACTIVE MEANS OVERLAPPING THE PERIOD, NOT "ACTIVE TODAY". An entitlement is
    charged for a period when [active_from, active_until] overlaps the period at
    all; active_until NULL means still active (023). Nothing here reads the
    clock except to default the period, which is what makes a past period
    reconstructible (§7.5) — re-running August's invoice in 2028 must produce
    August's answer, and it does, because deactivation sets active_until and
    never deletes.

  * NO PRORATION. A module active for any part of the period is charged in full
    for that period. A partial month of monitoring is still a month in which the
    obligation registry watched, alerted, and had to be right; billing half of
    it would imply we monitored half of it. The alternative — day-count
    proration — is a one-line change in `_module_line` if the commercial model
    later says otherwise, and the test that pins this is
    test_no_proration_a_module_active_for_one_day_costs_a_full_period.

  * AT MOST ONE CHARGE PER MODULE PER PERIOD. 023 permits a module to be
    dropped and re-bought, which is two entitlement rows that may both overlap
    one period. Two rows must not become two charges for one month of one
    module. The later window (by active_from) wins, since it carries the
    current commercial terms; the earlier is reported as an informational note.

  * A MODULE THAT CANNOT BE SOLD IS NOT BILLED, AND IS REPORTED LOUDLY. 023
    refuses status='available' unless provenance='verified', and refuses selling
    an 'unusable' module. An entitlement pointing at a module that is not
    sellable is a data problem, not a pricing case: charging for something we
    refused to make available would be indefensible, and silently skipping it
    would hide a broken entitlement. Such a line is excluded from the total,
    marked charged=False, and raises an `error` issue. Callers that must not
    proceed on bad data can use Invoice.has_errors or pass strict=True.
    'retired' is the one status that still bills — 023 is explicit that retiring
    a module leaves existing entitlements and their obligations alive, so the
    client is still monitored — but it raises a warning so it is visible.

Billing state is stored in the `organizations` table:
  site_limit               int    — LEGACY, no longer meters anything; see
                                    get_org_billing and UNLIMITED_SITES
  plan_name                text   — base / dev (legacy site tiers deprecated)
  payment_provider         text   — provider that owns the subscription
  payment_customer_id      text   — provider customer ID
  payment_subscription_id  text   — provider subscription / series anchor ID
  payment_source_id        text   — stored payment instrument (recurring)
  subscription_status      text   — active / past_due / cancelled / refunded
  next_billing_at          timestamptz — next merchant-initiated charge
  stripe_customer_id       text   — legacy Stripe columns (kept intact)
  stripe_subscription_id   text

KNOWN GAP, FLAGGED NOT BURIED. `payments/` charges `PLANS[plan_key]["price_usd"]`
— the base fee only. It has no org context and therefore cannot see the module
add-ons, and payments/ is out of scope for this change. Until a provider is
taught to ask `amount_due(org_id)`, the recurring charge is the base fee and the
module add-ons are invoiced out of band. `amount_due()` exists precisely so that
wiring is a one-line change inside the provider when it is in scope.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)


# ── The commercial model (§4.5, §8 decision 4) ───────────────────────────────

# The base platform fee: sites, users and the platform. UNDERSPECIFIED IN §4.5 —
# the document states the SHAPE (base + per-module) and never an amount. 199 is
# carried over from the old single-site tier so that no existing subscribed org
# sees its charge rise on the day this lands; it is a placeholder for a
# commercial decision, not a commercial decision.
BASE_PLATFORM_FEE_MONTHLY = Decimal("199")

# Module prices are NUMERIC in AED (023: guideline_modules.currency DEFAULT
# 'AED'). ALSO UNDERSPECIFIED, and a live inconsistency: payments/ hard-codes
# "currency": "USD" for the base-fee charge. Both are labelled here rather than
# reconciled, because reconciling them means touching payments/.
BILLING_CURRENCY = "AED"

# Sites no longer meter anything — the base fee covers them. 999 rather than a
# larger sentinel because frontend/src/components/Settings.tsx renders 999 as
# '∞'; changing the number would change the UI without changing the model.
UNLIMITED_SITES = 999

_TWOPLACES = Decimal("0.01")


# ── Plan catalogue ────────────────────────────────────────────────────────────
# One sellable base plan plus the developer plan. The three site-count tiers are
# RETAINED AS DEPRECATED ENTRIES and cannot be bought (see create_checkout_session):
# they are not dead weight — payments/checkout_provider.py and
# payments/stripe_provider.py both read PLANS["starter"] by name when cancelling a
# subscription, and orgs still carry plan_name='growth' in the database. Removing
# the keys would raise KeyError inside a provider this change may not modify, and
# rewriting their prices would silently re-tariff an existing subscriber. They
# price nothing new; `sellable_plans()` is what a checkout screen should offer.

PLANS: dict[str, dict] = {
    "base": {
        "name":        "Platform",
        "site_limit":  UNLIMITED_SITES,
        "price_usd":   int(BASE_PLATFORM_FEE_MONTHLY),
        "description": ("Base platform fee — unlimited sites and users. "
                        "Compliance modules are added per guideline."),
        "deprecated":  False,
    },
    "dev": {
        "name":        "Developer",
        "site_limit":  UNLIMITED_SITES,
        "price_usd":   0,
        "description": "Unlimited (development/testing)",
        "deprecated":  False,
    },
    # ── Deprecated site-count tiers (§8 decision 4). Not sellable. ────────────
    "starter": {
        "name":        "Starter (legacy)",
        "site_limit":  UNLIMITED_SITES,
        "price_usd":   199,
        "description": "Legacy site-count plan — replaced by the base platform fee.",
        "deprecated":  True,
    },
    "growth": {
        "name":        "Growth (legacy)",
        "site_limit":  UNLIMITED_SITES,
        "price_usd":   799,
        "description": "Legacy site-count plan — replaced by the base platform fee.",
        "deprecated":  True,
    },
    "professional": {
        "name":        "Professional (legacy)",
        "site_limit":  UNLIMITED_SITES,
        "price_usd":   1999,
        "description": "Legacy site-count plan — replaced by the base platform fee.",
        "deprecated":  True,
    },
}

DEFAULT_PLAN = "base"


def sellable_plans() -> dict[str, dict]:
    """The plans a client may actually buy today — the deprecated site-count
    tiers are excluded. A checkout screen should offer these, not PLANS."""
    return {k: v for k, v in PLANS.items() if not v.get("deprecated")}


def plan_is_sellable(plan_key: str) -> bool:
    plan = PLANS.get(plan_key)
    return bool(plan) and not plan.get("deprecated")


# ── Modular pricing: the pure core ───────────────────────────────────────────
# Everything below this line is a pure function of rows + a period. No clock, no
# database, no provider. That is what makes a past period reconstructible (§7.5)
# and what the tests exercise directly.

#: Module statuses (023 guideline_modules.status) and what billing does with each.
BILLABLE_STATUSES = ("available", "retired")

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class BillingIssue:
    """Something wrong enough that a human must see it. Never a silent skip."""
    severity: str            # error | warning | info
    code: str
    message: str
    entitlement_id: Optional[str] = None
    module_key: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"[{self.severity}] {self.code}: {self.message}"


@dataclass(frozen=True)
class LineItem:
    """One charge (or one refused charge) on an invoice."""
    kind: str                       # "base" | "module"
    label: str
    amount: Decimal
    currency: str
    charged: bool
    price_source: str               # "base" | "agreed" | "list" | "none"
    module_id: Optional[str] = None
    module_key: Optional[str] = None
    entitlement_id: Optional[str] = None
    reason: str = ""                # why it is not charged, when it is not


@dataclass(frozen=True)
class Invoice:
    organization_id: str
    period_start: date
    period_end: date
    currency: str
    base_fee: Decimal
    total: Decimal
    lines: tuple[LineItem, ...] = ()
    issues: tuple[BillingIssue, ...] = ()

    @property
    def module_lines(self) -> tuple[LineItem, ...]:
        return tuple(l for l in self.lines if l.kind == "module")

    @property
    def charged_modules(self) -> tuple[LineItem, ...]:
        return tuple(l for l in self.module_lines if l.charged)

    @property
    def modules_charged(self) -> int:
        return len(self.charged_modules)

    @property
    def errors(self) -> tuple[BillingIssue, ...]:
        return tuple(i for i in self.issues if i.severity == ERROR)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def as_dict(self) -> dict:
        """JSON-safe shape for an API response or an audit record."""
        return {
            "organization_id": self.organization_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "currency": self.currency,
            "base_fee": str(self.base_fee),
            "total": str(self.total),
            "modules_charged": self.modules_charged,
            "lines": [
                {
                    "kind": l.kind, "label": l.label, "amount": str(l.amount),
                    "currency": l.currency, "charged": l.charged,
                    "price_source": l.price_source, "module_key": l.module_key,
                    "module_id": l.module_id, "entitlement_id": l.entitlement_id,
                    "reason": l.reason,
                }
                for l in self.lines
            ],
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message,
                 "entitlement_id": i.entitlement_id, "module_key": i.module_key}
                for i in self.issues
            ],
        }


class BillingDataError(Exception):
    """Raised by price_period(strict=True) when an invoice carries errors."""

    def __init__(self, issues: Sequence[BillingIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(str(i) for i in self.issues))


def _as_date(value: Any) -> Optional[date]:
    """Accept a date, a datetime, or an ISO string (PostgREST returns strings)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_money(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(_TWOPLACES, rounding=ROUND_HALF_UP)
    except Exception:
        return None


def month_period(on: Optional[date] = None) -> tuple[date, date]:
    """The calendar month containing `on` (today by default), inclusive."""
    on = on or date.today()
    return (date(on.year, on.month, 1),
            date(on.year, on.month, calendar.monthrange(on.year, on.month)[1]))


def entitlement_active_in(entitlement: Mapping[str, Any],
                          period_start: date, period_end: date) -> bool:
    """Did this entitlement overlap the period at all?

    NULL active_until means still active (023). active_from is NOT NULL in the
    schema; a row arriving without one is treated as never active rather than
    as always active, because guessing the start of a commercial agreement in
    the permissive direction bills someone for time nobody agreed to.
    """
    start = _as_date(entitlement.get("active_from"))
    if start is None or start > period_end:
        return False
    end = _as_date(entitlement.get("active_until"))
    return end is None or end >= period_start


def module_price(entitlement: Mapping[str, Any],
                 module: Mapping[str, Any]) -> tuple[Optional[Decimal], str]:
    """(price, source). price_agreed where set, list price otherwise — 023 says
    NULL price_agreed means list price. A price_agreed of 0 is a real agreement
    (023 allows >= 0) and must not fall through to the list price, which is why
    this tests for None rather than for falsiness."""
    agreed = _as_money(entitlement.get("price_agreed"))
    if agreed is not None:
        return agreed, "agreed"
    listed = _as_money(module.get("list_price_monthly"))
    if listed is not None:
        return listed, "list"
    return None, "none"


def _module_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """The joined guideline_modules row. Accepts either a PostgREST nested
    object under 'guideline_modules'/'module', or a pre-flattened mapping."""
    nested = row.get("guideline_modules") or row.get("module")
    if isinstance(nested, list):
        nested = nested[0] if nested else None
    if isinstance(nested, Mapping):
        return nested
    return row


def _sellability(module: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    """(code, message) when this module must NOT be billed, else None."""
    status = (module.get("status") or "").strip()
    kind = (module.get("module_kind") or "").strip()
    provenance = (module.get("provenance") or "").strip()
    if kind == "unusable":
        return ("module_unusable",
                "module_kind='unusable' — 023 refuses to sell it and it can "
                "deliver nothing; the entitlement should never have existed")
    if status not in BILLABLE_STATUSES:
        return ("module_not_available",
                f"module status is {status or 'unknown'!r}, not available — "
                "an entitlement exists for a module that was never put on sale")
    if status == "available" and provenance != "verified":
        return ("module_unverified",
                f"module is available with provenance {provenance or 'unknown'!r} — "
                "023's verified_to_sell check should make this impossible")
    return None


def price_period(
    organization_id: str,
    entitlements: Iterable[Mapping[str, Any]],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    *,
    base_fee: Optional[Decimal] = None,
    currency: str = BILLING_CURRENCY,
    strict: bool = False,
) -> Invoice:
    """Price one organisation for one period. Pure — see the module docstring.

    `entitlements` are organization_entitlements rows, each carrying its joined
    guideline_modules row (nested under 'guideline_modules', or flattened).

    Charges the base platform fee plus one add-on per active, sellable module.
    Inactive entitlements are silently absent (that is the normal, correct
    case); unsellable modules are excluded from the total and REPORTED.
    """
    if period_start is None:
        period_start, default_end = month_period()
        period_end = period_end or default_end
    elif period_end is None:
        period_end = month_period(period_start)[1]
    if period_end < period_start:
        raise ValueError("period_end precedes period_start")

    fee = _as_money(BASE_PLATFORM_FEE_MONTHLY if base_fee is None else base_fee)
    fee = fee if fee is not None else Decimal("0.00")

    lines: list[LineItem] = [LineItem(
        kind="base", label="Base platform fee — sites, users and platform",
        amount=fee, currency=currency, charged=True, price_source="base",
    )]
    issues: list[BillingIssue] = []

    # At most one charge per module per period (see the module docstring).
    by_module: dict[str, dict] = {}
    for row in entitlements:
        if not entitlement_active_in(row, period_start, period_end):
            continue
        module = _module_of(row)
        key = str(module.get("id") or module.get("key")
                  or row.get("module_id") or row.get("id"))
        previous = by_module.get(key)
        if previous is None:
            by_module[key] = {"row": row, "module": module}
            continue
        keep, drop = previous["row"], row
        if (_as_date(row.get("active_from")) or date.min) > \
           (_as_date(previous["row"].get("active_from")) or date.min):
            keep, drop = row, previous["row"]
            by_module[key] = {"row": row, "module": module}
        issues.append(BillingIssue(
            INFO, "duplicate_entitlement_window",
            "two entitlement windows for one module overlap this period; the "
            f"later one ({keep.get('id')}) is charged and {drop.get('id')} is not",
            entitlement_id=str(drop.get("id") or ""),
            module_key=module.get("key"),
        ))

    total = fee
    for entry in by_module.values():
        row, module = entry["row"], entry["module"]
        label = module.get("label") or module.get("key") or "Unnamed module"
        ent_id = str(row.get("id") or "") or None
        mod_key = module.get("key")
        mod_id = str(module.get("id") or "") or None

        blocked = _sellability(module)
        if blocked:
            code, message = blocked
            issues.append(BillingIssue(ERROR, code, message,
                                       entitlement_id=ent_id, module_key=mod_key))
            logger.error("billing: org %s entitlement %s module %s not billed — %s",
                         organization_id, ent_id, mod_key, message)
            lines.append(LineItem("module", label, Decimal("0.00"), currency,
                                  charged=False, price_source="none",
                                  module_id=mod_id, module_key=mod_key,
                                  entitlement_id=ent_id, reason=message))
            continue

        if (module.get("status") or "") == "retired":
            issues.append(BillingIssue(
                WARNING, "module_retired",
                "module is retired but the entitlement is still active, so "
                "monitoring continues and the add-on is still charged (023) — "
                "close the entitlement to stop both",
                entitlement_id=ent_id, module_key=mod_key))

        price, source = module_price(row, module)
        if price is None:
            message = ("no price: entitlement.price_agreed and module."
                       "list_price_monthly are both NULL, so there is no amount "
                       "to charge and none may be invented")
            issues.append(BillingIssue(ERROR, "module_unpriced", message,
                                       entitlement_id=ent_id, module_key=mod_key))
            logger.error("billing: org %s module %s has no price", organization_id, mod_key)
            lines.append(LineItem("module", label, Decimal("0.00"), currency,
                                  charged=False, price_source="none",
                                  module_id=mod_id, module_key=mod_key,
                                  entitlement_id=ent_id, reason=message))
            continue

        mod_currency = (module.get("currency") or currency).strip() or currency
        if mod_currency != currency:
            message = (f"module priced in {mod_currency} on an invoice in "
                       f"{currency}; no conversion rate is defined, so the line "
                       "is not charged")
            issues.append(BillingIssue(ERROR, "currency_mismatch", message,
                                       entitlement_id=ent_id, module_key=mod_key))
            logger.error("billing: org %s module %s currency mismatch (%s vs %s)",
                         organization_id, mod_key, mod_currency, currency)
            lines.append(LineItem("module", label, price, mod_currency,
                                  charged=False, price_source=source,
                                  module_id=mod_id, module_key=mod_key,
                                  entitlement_id=ent_id, reason=message))
            continue

        lines.append(LineItem("module", label, price, currency, charged=True,
                              price_source=source, module_id=mod_id,
                              module_key=mod_key, entitlement_id=ent_id))
        total += price

    invoice = Invoice(
        organization_id=organization_id,
        period_start=period_start, period_end=period_end,
        currency=currency, base_fee=fee,
        total=total.quantize(_TWOPLACES, rounding=ROUND_HALF_UP),
        lines=tuple(lines), issues=tuple(issues),
    )
    if strict and invoice.has_errors:
        raise BillingDataError(invoice.errors)
    return invoice


# ── Modular pricing: the database edge ───────────────────────────────────────

_ENTITLEMENT_COLUMNS = (
    "id, organization_id, module_id, active_from, active_until, price_agreed, "
    "guideline_modules(id, key, label, category, module_kind, status, "
    "provenance, list_price_monthly, currency)"
)


def fetch_entitlements(org_id: str, client=None) -> list[dict]:
    """Every entitlement row for an org — INCLUDING deactivated ones, because a
    past period must remain reconstructible (§7.5). The period filter is applied
    in `price_period`, not here; filtering to "active now" in the query is
    precisely what would make last year's invoice unreproducible."""
    if client is None:
        from db.client import get_client
        client = get_client()
    if not client:
        return []
    try:
        res = (client.table("organization_entitlements")
               .select(_ENTITLEMENT_COLUMNS)
               .eq("organization_id", org_id)
               .execute())
        return list(res.data or [])
    except Exception:
        logger.exception("billing: could not read entitlements for org %s", org_id)
        return []


def compute_invoice(org_id: str, period_start: Optional[date] = None,
                    period_end: Optional[date] = None, *, client=None,
                    base_fee: Optional[Decimal] = None,
                    strict: bool = False) -> Invoice:
    """The org's invoice for a period (the current calendar month by default).

    Reconstructible: pass a past period and the answer is what it was, because
    entitlements are deactivated by setting active_until and never deleted."""
    rows = fetch_entitlements(org_id, client=client)
    return price_period(org_id, rows, period_start, period_end,
                        base_fee=base_fee, strict=strict)


def amount_due(org_id: str, on: Optional[date] = None, *, client=None) -> Decimal:
    """Total for the calendar month containing `on` — base fee plus add-ons.

    This is the number a payment provider should charge. It is not wired into
    payments/ yet: see the KNOWN GAP in the module docstring."""
    start, end = month_period(on)
    return compute_invoice(org_id, start, end, client=client).total


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
    """Fetch billing fields from the organizations table.

    `site_limit` is reported as UNLIMITED_SITES regardless of the stored column
    (§8 decision 4): sites are covered by the base platform fee and no longer
    meter anything, so the api_server gate that reads this key can no longer
    refuse a site. The stored value is still returned, under
    `site_limit_stored`, so nothing loses the record — payments/ writes it on
    cancellation and this function is the only thing that reads it."""
    from db.client import get_client
    client = get_client()
    if not client:
        return {"site_limit": UNLIMITED_SITES, "site_limit_stored": None,
                "plan_name": DEFAULT_PLAN}
    data: dict = {}
    for columns in (_BILLING_COLUMNS, _LEGACY_COLUMNS):
        try:
            res = client.table("organizations").select(columns).eq("id", org_id).single().execute()
            data = res.data or {}
            break
        except Exception:
            continue
    if not data:
        return {"site_limit": UNLIMITED_SITES, "site_limit_stored": None,
                "plan_name": DEFAULT_PLAN}
    return {
        "site_limit": UNLIMITED_SITES,
        "site_limit_stored": data.get("site_limit"),
        "plan_name": data.get("plan_name") or DEFAULT_PLAN,
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
