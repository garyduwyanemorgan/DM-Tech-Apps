"""Modular billing: base platform fee plus one add-on per entitled module.

§8 decision 4 / §4.5. The site-count tiers are gone; what is charged is
`organization_entitlements` joined to `guideline_modules`, and the load-bearing
assertions are about what must NOT be charged:

  * an entitlement whose window does not overlap the period (§7.5 — a client who
    un-ticked a module in June is not billed for it in August, and the row is
    still there, so June remains reconstructible);
  * a module that 023 would refuse to sell, which is a data problem that must be
    reported rather than quietly charged or quietly dropped.

Pure functions and a fake client — no database, no network, in the style of
tests/test_load_guidelines.py.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import billing
from billing import (
    BASE_PLATFORM_FEE_MONTHLY, BillingDataError, ERROR, UNLIMITED_SITES,
    compute_invoice, entitlement_active_in, module_price, month_period,
    plan_is_sellable, price_period, sellable_plans,
)

ORG = "org-1"
AUG_START, AUG_END = date(2026, 8, 1), date(2026, 8, 31)
BASE = BASE_PLATFORM_FEE_MONTHLY


def module(**kw) -> dict:
    base = {"id": "mod-1", "key": "gu44_water_systems", "label": "GU44 Water Systems",
            "module_kind": "compliance", "status": "available",
            "provenance": "verified", "list_price_monthly": "300.00",
            "currency": "AED"}
    base.update(kw)
    return base


def entitlement(mod=None, **kw) -> dict:
    row = {"id": "ent-1", "organization_id": ORG, "module_id": (mod or module())["id"],
           "active_from": "2026-01-01", "active_until": None, "price_agreed": None,
           "guideline_modules": mod or module()}
    row.update(kw)
    return row


def price(rows, **kw):
    return price_period(ORG, rows, AUG_START, AUG_END, **kw)


# ── The base fee ─────────────────────────────────────────────────────────────

def test_base_fee_alone_when_no_modules_are_entitled():
    inv = price([])
    assert inv.total == BASE
    assert inv.modules_charged == 0
    assert [l.kind for l in inv.lines] == ["base"]
    assert inv.issues == ()


def test_the_empty_case_is_a_valid_invoice_not_a_crash():
    """An org with nothing ticked still owes the platform fee, and the invoice
    is well formed enough to render."""
    inv = price([])
    assert Decimal(inv.as_dict()["total"]) == BASE
    assert inv.as_dict()["lines"][0]["kind"] == "base"
    assert not inv.has_errors


# ── Base plus N modules — the whole point of the change ──────────────────────

def test_base_plus_one_module():
    inv = price([entitlement()])
    assert inv.total == BASE + Decimal("300.00")
    assert inv.modules_charged == 1


def test_the_charge_rises_with_the_number_of_modules_ticked():
    rows = [
        entitlement(module(id="m1", key="gu44"), id="e1"),
        entitlement(module(id="m2", key="gu119", list_price_monthly="150"), id="e2"),
        entitlement(module(id="m3", key="gu81", list_price_monthly="50"), id="e3"),
    ]
    totals = [price(rows[:n]).total for n in range(len(rows) + 1)]
    assert totals == [BASE, BASE + Decimal("300"), BASE + Decimal("450"),
                      BASE + Decimal("500")]
    assert all(b < a for b, a in zip(totals, totals[1:]))


def test_nothing_is_priced_from_a_site_count():
    """The old model. There is no site input to pricing at all now."""
    inv = price([entitlement()])
    assert "site" not in inv.as_dict()["lines"][1]["label"].lower()
    assert "starter" not in sellable_plans()          # legacy tier not sellable
    assert "professional" not in sellable_plans()
    assert not plan_is_sellable("growth")
    assert billing.PLANS["base"]["site_limit"] == UNLIMITED_SITES


# ── price_agreed overrides the list price ────────────────────────────────────

def test_price_agreed_overrides_list_price():
    inv = price([entitlement(price_agreed="120.00")])
    assert inv.total == BASE + Decimal("120.00")
    assert inv.module_lines[0].price_source == "agreed"


def test_null_price_agreed_means_list_price():
    """023 says so outright."""
    assert module_price({"price_agreed": None}, module())[0] == Decimal("300.00")
    assert module_price({"price_agreed": None}, module())[1] == "list"


def test_an_agreed_price_of_zero_is_an_agreement_not_a_missing_value():
    """A free module is a real commercial arrangement; falling through to the
    list price here would invoice a client for something given away."""
    inv = price([entitlement(price_agreed="0")])
    assert inv.total == BASE
    assert inv.modules_charged == 1
    assert inv.module_lines[0].price_source == "agreed"


def test_a_module_with_no_price_anywhere_is_reported_not_guessed():
    inv = price([entitlement(module(list_price_monthly=None))])
    assert inv.total == BASE
    assert [i.code for i in inv.errors] == ["module_unpriced"]
    assert inv.module_lines[0].charged is False


# ── Active windows (§7.5) ────────────────────────────────────────────────────

def test_an_inactive_entitlement_is_not_charged():
    inv = price([entitlement(active_from="2026-01-01", active_until="2026-06-30")])
    assert inv.total == BASE
    assert inv.modules_charged == 0
    assert not inv.has_errors          # ordinary, correct, not a data problem


def test_an_entitlement_starting_after_the_period_is_not_charged():
    inv = price([entitlement(active_from="2026-09-01")])
    assert inv.total == BASE


def test_null_active_until_means_still_active():
    assert entitlement_active_in({"active_from": "2020-01-01", "active_until": None},
                                 AUG_START, AUG_END)


def test_an_entitlement_with_no_start_date_is_never_charged():
    """active_from is NOT NULL in 023. If one arrives without it, the safe
    direction is 'not yet billing' — the other direction invoices someone for
    time nobody agreed to."""
    assert not entitlement_active_in({"active_from": None}, AUG_START, AUG_END)


def test_no_proration_a_module_active_for_one_day_costs_a_full_period():
    """The documented decision (see billing.py's module docstring). Change the
    rule there and this test is where it is pinned."""
    inv = price([entitlement(active_from="2026-08-31")])
    assert inv.total == BASE + Decimal("300.00")
    ended = price([entitlement(active_from="2026-01-01", active_until="2026-08-01")])
    assert ended.total == BASE + Decimal("300.00")


def test_a_past_period_is_reconstructible_from_the_same_rows():
    """§7.5: deactivation retains history, so re-running an old period gives the
    old answer — the row that stopped billing in July still prices June."""
    rows = [entitlement(active_from="2026-01-01", active_until="2026-06-30")]
    june = price_period(ORG, rows, date(2026, 6, 1), date(2026, 6, 30))
    august = price_period(ORG, rows, AUG_START, AUG_END)
    assert june.total == BASE + Decimal("300.00")
    assert august.total == BASE
    assert price_period(ORG, rows, date(2026, 6, 1), date(2026, 6, 30)).total == june.total


def test_one_module_bought_dropped_and_rebought_is_charged_once():
    mod = module()
    rows = [entitlement(mod, id="old", active_from="2026-01-01", active_until="2026-08-10"),
            entitlement(mod, id="new", active_from="2026-08-11", price_agreed="400")]
    inv = price(rows)
    assert inv.modules_charged == 1
    assert inv.total == BASE + Decimal("400")          # the later window's terms
    assert [i.code for i in inv.issues] == ["duplicate_entitlement_window"]


# ── A module that cannot be sold must not be billed ──────────────────────────

def test_a_coming_soon_module_is_flagged_and_not_charged():
    inv = price([entitlement(module(status="coming_soon", provenance="unverified"))])
    assert inv.total == BASE
    assert inv.has_errors
    assert inv.errors[0].code == "module_not_available"
    assert inv.errors[0].module_key == "gu44_water_systems"
    assert inv.module_lines[0].charged is False
    assert inv.module_lines[0].reason                  # never a silent skip


def test_an_unusable_module_is_flagged_and_not_charged():
    """023 refuses to sell an 'unusable' module (GU141 contradicts itself)."""
    inv = price([entitlement(module(module_kind="unusable", status="coming_soon"))])
    assert inv.total == BASE
    assert [i.code for i in inv.errors] == ["module_unusable"]


def test_an_available_but_unverified_module_is_flagged():
    """023's verified_to_sell check should make this unreachable. If the row
    exists anyway, billing says so rather than trusting it."""
    inv = price([entitlement(module(provenance="unverified"))])
    assert [i.code for i in inv.errors] == ["module_unverified"]
    assert inv.total == BASE


def test_strict_mode_refuses_to_produce_an_invoice_over_bad_data():
    with pytest.raises(BillingDataError):
        price([entitlement(module(status="coming_soon", provenance="unverified"))],
              strict=True)


def test_a_retired_module_still_bills_but_warns():
    """023: retiring a module leaves existing entitlements and their obligations
    alive, so the client is still monitored and still charged — visibly."""
    inv = price([entitlement(module(status="retired"))])
    assert inv.total == BASE + Decimal("300.00")
    assert [i.severity for i in inv.issues] == ["warning"]
    assert not inv.has_errors


def test_a_module_priced_in_another_currency_is_not_converted_silently():
    inv = price([entitlement(module(currency="USD"))])
    assert inv.total == BASE
    assert [i.code for i in inv.errors] == ["currency_mismatch"]


# ── The database edge ────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters: list[tuple[str, object]] = []

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def execute(self):
        return FakeResponse([r for r in self.rows
                             if all(r.get(c) == v for c, v in self.filters)])


class FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "organization_entitlements"
        return FakeQuery(self.rows)


def test_compute_invoice_reads_entitlements_including_deactivated_ones():
    """The period filter must be applied in pricing, not in the query — a query
    that asked only for 'active now' rows could not reconstruct a past period."""
    rows = [entitlement(id="e1"),
            entitlement(module(id="m2", key="gu119", list_price_monthly="100"),
                        id="e2", active_from="2026-01-01", active_until="2026-02-01")]
    inv = compute_invoice(ORG, AUG_START, AUG_END, client=FakeClient(rows))
    assert inv.total == BASE + Decimal("300.00")
    feb = compute_invoice(ORG, date(2026, 2, 1), date(2026, 2, 28),
                          client=FakeClient(rows))
    assert feb.total == BASE + Decimal("400.00")


def test_an_org_with_no_entitlement_rows_yields_the_base_fee():
    inv = compute_invoice(ORG, AUG_START, AUG_END, client=FakeClient([]))
    assert inv.total == BASE
    assert inv.modules_charged == 0


def test_a_broken_query_yields_the_base_fee_rather_than_an_exception():
    class Exploding(FakeClient):
        def table(self, name):
            raise RuntimeError("PostgREST is down")

    inv = compute_invoice(ORG, AUG_START, AUG_END, client=Exploding([]))
    assert inv.total == BASE


def test_month_period_and_default_period():
    assert month_period(date(2026, 2, 15)) == (date(2026, 2, 1), date(2026, 2, 28))
    inv = price_period(ORG, [])                    # defaults to the current month
    assert inv.period_start.day == 1
    assert inv.period_end >= inv.period_start


def test_a_period_end_before_its_start_is_refused():
    with pytest.raises(ValueError):
        price_period(ORG, [], AUG_END, AUG_START)
