"""The ageing engine — where the product's central claim is either true or not.

The tests that matter most here are the ones asserting that missing information
never reads as compliant. A registry whose job is noticing absence fails in one
direction: by reassuring.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.obligations import (
    COMPLIANT, DUE_SOON, EVENT_TRIGGERED, OVERDUE, PERIODIC, SELF_DECLARED_REVIEW,
    SUSPENDED, add_months, cadence_kind, due_soon_window, evaluate, next_due_after,
    satisfy, summarise,
)

TODAY = date(2026, 8, 15)


def periodic(months=None, days=None, **kw):
    return {"cadence_months": months, "cadence_days": days, "grace_days": 0, **kw}


# ── add_months: month-end clamping ───────────────────────────────────────────

@pytest.mark.parametrize("start,months,expected", [
    (date(2026, 1, 31), 1, date(2026, 2, 28)),   # not 3 March
    (date(2028, 1, 31), 1, date(2028, 2, 29)),   # leap year
    (date(2026, 8, 31), 6, date(2027, 2, 28)),
    (date(2026, 8, 15), 12, date(2027, 8, 15)),
    (date(2026, 12, 15), 1, date(2027, 1, 15)),  # year rollover
    (date(2026, 8, 15), 0, date(2026, 8, 15)),
])
def test_add_months_clamps_to_month_end(start, months, expected):
    assert add_months(start, months) == expected


def test_a_month_end_obligation_does_not_drift():
    """31 Jan monthly must stay on month ends, not walk forward every short month."""
    d = date(2026, 1, 31)
    seen = [d := add_months(d, 1) for _ in range(4)]
    assert seen == [date(2026, 2, 28), date(2026, 3, 28),
                    date(2026, 4, 28), date(2026, 5, 28)]


# ── The three kinds ──────────────────────────────────────────────────────────

def test_cadence_kind_identifies_each():
    assert cadence_kind(periodic(months=6)) == PERIODIC
    assert cadence_kind({"trigger_event": "after tank disinfection"}) == EVENT_TRIGGERED
    assert cadence_kind({"self_declared_review": True}) == SELF_DECLARED_REVIEW
    assert cadence_kind({"trigger_event": "   "}) == SELF_DECLARED_REVIEW


# ── Nothing missing may read as compliant ────────────────────────────────────

def test_unscheduled_periodic_is_overdue_and_flagged():
    """The silent-pass trap: a periodic duty nobody ever scheduled."""
    r = evaluate(periodic(months=6, next_due_on=None), TODAY)
    assert r.status == OVERDUE
    assert r.needs_attention is True
    assert "never scheduled" in r.reason


def test_self_declared_review_is_not_late_but_needs_attention():
    """The guideline states the duty and no frequency — 41 of these exist."""
    r = evaluate({"self_declared_review": True, "next_due_on": None}, TODAY)
    assert r.status == COMPLIANT
    assert r.needs_attention is True
    assert "no frequency" in r.reason


def test_event_triggered_awaiting_its_trigger_is_genuinely_clean():
    """The one case where no due date really does mean nothing outstanding."""
    r = evaluate({"trigger_event": "after tank disinfection", "next_due_on": None}, TODAY)
    assert r.status == COMPLIANT
    assert r.needs_attention is False
    assert "awaiting trigger" in r.reason


def test_a_fired_trigger_ages_like_anything_else():
    r = evaluate({"trigger_event": "after tank disinfection",
                  "next_due_on": date(2026, 7, 1), "grace_days": 0}, TODAY)
    assert r.status == OVERDUE


# ── Due / due soon / overdue ─────────────────────────────────────────────────

@pytest.mark.parametrize("due,expected", [
    (date(2026, 12, 1), COMPLIANT),   # far off
    (date(2026, 8, 20), DUE_SOON),    # inside the window
    (date(2026, 8, 15), DUE_SOON),    # today
    (date(2026, 8, 14), OVERDUE),     # yesterday, no grace
])
def test_status_by_due_date(due, expected):
    assert evaluate(periodic(months=6, next_due_on=due), TODAY).status == expected


def test_grace_delays_overdue_without_hiding_it():
    ob = periodic(months=6, next_due_on=date(2026, 8, 10), grace_days=7)
    r = evaluate(ob, TODAY)
    assert r.status == DUE_SOON            # 5 days past due, inside 7-day grace
    assert "grace" in r.reason
    assert r.days_until_due == -5
    assert evaluate({**ob, "next_due_on": date(2026, 8, 1)}, TODAY).status == OVERDUE


def test_iso_string_due_dates_are_accepted():
    """PostgREST returns dates as strings."""
    assert evaluate(periodic(months=6, next_due_on="2026-12-01"), TODAY).status == COMPLIANT


def test_suspended_is_never_aged():
    """§7.5 — un-ticking a module stops monitoring, visibly, not quietly."""
    r = evaluate(periodic(months=6, next_due_on=date(2020, 1, 1), status=SUSPENDED), TODAY)
    assert r.status == SUSPENDED
    assert r.needs_attention is False


# ── The due-soon window scales with the cadence ──────────────────────────────

def test_window_is_capped_at_the_default_for_long_cadences():
    assert due_soon_window(periodic(months=12)) == 30


def test_window_shrinks_for_short_cadences():
    """A 30-day warning on a 7-day duty is the same as no warning at all."""
    assert due_soon_window(periodic(days=7)) == 1
    assert due_soon_window(periodic(days=28)) == 7


def test_a_weekly_obligation_is_not_permanently_due_soon():
    ob = periodic(days=7, next_due_on=date(2026, 8, 20))
    assert evaluate(ob, TODAY).status == COMPLIANT   # 5 days out, window is 1


# ── Satisfaction ─────────────────────────────────────────────────────────────

def test_satisfying_reschedules_from_the_satisfied_date():
    """Not from the due date — late evidence must not stack a second deadline."""
    ob = periodic(months=6, next_due_on=date(2026, 6, 1))
    patch = satisfy(ob, date(2026, 8, 15), "abc", "lab_sample")
    assert patch["next_due_on"] == "2027-02-15"
    assert patch["last_satisfied_by"] == "abc"
    assert patch["last_satisfied_kind"] == "lab_sample"


def test_satisfying_an_event_triggered_obligation_clears_its_due_date():
    ob = {"trigger_event": "after repair", "next_due_on": date(2026, 8, 1)}
    assert satisfy(ob, date(2026, 8, 15))["next_due_on"] is None


def test_next_due_after_handles_both_cadence_units():
    assert next_due_after(date(2026, 8, 15), periodic(months=3)) == date(2026, 11, 15)
    assert next_due_after(date(2026, 8, 15), periodic(days=90)) == date(2026, 11, 13)


# ── Summary ──────────────────────────────────────────────────────────────────

def test_needs_attention_is_not_folded_into_overdue():
    """'you are late' and 'we cannot tell' are different conversations."""
    obs = [
        periodic(months=6, next_due_on=date(2026, 12, 1)),   # compliant
        periodic(months=6, next_due_on=date(2026, 8, 20)),   # due soon
        periodic(months=6, next_due_on=date(2026, 1, 1)),    # overdue
        periodic(months=6, next_due_on=None),                # overdue + attention
        {"self_declared_review": True, "next_due_on": None}, # compliant + attention
    ]
    s = summarise(obs, TODAY)
    assert s[COMPLIANT] == 2 and s[DUE_SOON] == 1 and s[OVERDUE] == 2
    assert s["needs_attention"] == 2
    assert s["total"] == 5


def test_satisfy_refuses_a_half_recorded_evidence_reference():
    """023's satisfied_pair_check rejects it; catch it before the round trip.

    A kind with no id names a category of evidence nobody can produce, and an id
    with no kind cannot be resolved to a table — §4.3 makes the reference
    polymorphic with no foreign key to disambiguate it.
    """
    ob = periodic(months=1)
    with pytest.raises(ValueError, match="together"):
        satisfy(ob, TODAY, evidence_id=None, evidence_kind="inspection")
    with pytest.raises(ValueError, match="together"):
        satisfy(ob, TODAY, evidence_id="abc", evidence_kind=None)


def test_satisfy_with_no_evidence_reference_is_allowed():
    """Not every duty produces a document — a completion date can stand alone."""
    patch = satisfy(periodic(months=1), TODAY)
    assert patch["last_satisfied_by"] is None
    assert patch["last_satisfied_kind"] is None
    assert patch["last_satisfied_at"] == "2026-08-15"
