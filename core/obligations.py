"""Ageing an obligation: when is it due, and is it late.

This is the engine behind the claim the whole product rests on. The app already
knew what a certificate *said*; §4.3 is about knowing a certificate was **due and
never arrived**. For an FM contractor that inversion is the value — the risk is
the missing test, not the failed one.

Pure functions, no IO, no database. `today` is always a parameter and never
`date.today()`, so every result is reproducible and testable, and a report
rendered for an audit can be re-rendered identically later.

THREE KINDS OF OBLIGATION, which migration 023's obligations_cadence_check
enforces as mutually exclusive:

  periodic              a cadence is set; due again every N months or days
  event_triggered       no cadence; becomes due when a named event occurs
  self_declared_review  neither; the guideline states a duty but no frequency

The third exists because the guidelines demanded it. Loading the corpus found 41
obligations stating a duty with no frequency at all — "the grease trap must be
cleaned", with no interval. They cannot be aged from the document alone, and
pretending otherwise would either invent a deadline nobody agreed to or leave a
row that silently never comes due.

WHAT NEVER HAPPENS HERE
-----------------------
**No status is ever inferred to be `compliant` from missing data.** A periodic
obligation with no `next_due_on` has never been scheduled; that is a gap in
configuration, not a clean record, and it is reported as needing attention. The
same reasoning that made `status` NOT NULL with no default in 023, and that makes
`resolve_limits` return None rather than a default in §7.4: in a registry whose
job is noticing absence, the dangerous answer is the reassuring one.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Mapping, NamedTuple, Optional

COMPLIANT = "compliant"
DUE_SOON = "due_soon"
OVERDUE = "overdue"
SUSPENDED = "suspended"
STATUSES = (COMPLIANT, DUE_SOON, OVERDUE, SUSPENDED)

PERIODIC = "periodic"
EVENT_TRIGGERED = "event_triggered"
SELF_DECLARED_REVIEW = "self_declared_review"

# How much warning "due soon" gives, by default. Capped against the cadence
# itself: a 30-day horizon on a 7-day inspection would leave it permanently
# due_soon, which is the same as no warning at all. A quarter of the interval is
# the compromise — enough notice to book a laboratory, short enough that the
# state still means something on a short cycle.
DEFAULT_DUE_SOON_DAYS = 30
DUE_SOON_FRACTION = 0.25


class ObligationStatus(NamedTuple):
    status: str
    kind: str
    reason: str
    days_until_due: Optional[int]   # negative once past due; None when unscheduled
    needs_attention: bool           # a data problem, distinct from being late


def add_months(start: date, months: int) -> date:
    """Add whole months, clamping to the end of a short month.

    31 January + 1 month is 28 February (or the 29th in a leap year), not
    3 March. A sampling obligation set on the 31st must not silently drift
    forward a few days every short month until it has skipped a period.
    """
    if months == 0:
        return start
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def cadence_kind(obligation: Mapping[str, Any]) -> str:
    """Which of the three kinds this is, per 023's cadence CHECK."""
    if obligation.get("cadence_months") or obligation.get("cadence_days"):
        return PERIODIC
    if (obligation.get("trigger_event") or "").strip():
        return EVENT_TRIGGERED
    if obligation.get("self_declared_review"):
        return SELF_DECLARED_REVIEW
    # The CHECK makes this unreachable from the database, but this function is
    # also given un-persisted rows during loading.
    return SELF_DECLARED_REVIEW


def cadence_in_days(obligation: Mapping[str, Any]) -> Optional[int]:
    """Approximate interval length, for sizing the due-soon window only.

    Deliberately approximate — 30 days to a month. It is never used to compute a
    due DATE, which always goes through add_months so month lengths are exact.
    """
    if obligation.get("cadence_days"):
        return int(obligation["cadence_days"])
    if obligation.get("cadence_months"):
        return int(obligation["cadence_months"]) * 30
    return None


def next_due_after(satisfied_on: date, obligation: Mapping[str, Any]) -> Optional[date]:
    """When a periodic obligation falls due again, having just been satisfied.

    Measured from the date it was SATISFIED, not from the date it was previously
    due. Those differ whenever evidence arrives late, and measuring from the due
    date would stack a second deadline on top of a breach the client is already
    dealing with. Measuring from satisfaction is also how a laboratory schedule
    actually works.
    """
    if obligation.get("cadence_months"):
        return add_months(satisfied_on, int(obligation["cadence_months"]))
    if obligation.get("cadence_days"):
        return satisfied_on + timedelta(days=int(obligation["cadence_days"]))
    return None


def due_soon_window(obligation: Mapping[str, Any],
                    default_days: int = DEFAULT_DUE_SOON_DAYS) -> int:
    """How many days before the due date the obligation starts warning."""
    interval = cadence_in_days(obligation)
    if not interval:
        return default_days
    return max(1, min(default_days, int(interval * DUE_SOON_FRACTION)))


def evaluate(obligation: Mapping[str, Any], today: date,
             default_days: int = DEFAULT_DUE_SOON_DAYS) -> ObligationStatus:
    """Age one obligation as at `today`."""
    kind = cadence_kind(obligation)

    # A suspended obligation is not monitored and must not be aged. §7.5: a
    # client who un-ticks a module stops being monitored, which is commercially
    # correct — but it must be visibly suspended, never quietly compliant.
    if obligation.get("status") == SUSPENDED:
        return ObligationStatus(
            SUSPENDED, kind,
            "entitlement inactive — not monitored, and history retained",
            None, needs_attention=False)

    grace = int(obligation.get("grace_days") or 0)
    due = obligation.get("next_due_on")
    if isinstance(due, str):
        due = date.fromisoformat(due)

    if due is None:
        if kind == EVENT_TRIGGERED:
            # Nothing is owed until the event happens. This is the one case where
            # "no due date" genuinely means "nothing outstanding".
            return ObligationStatus(
                COMPLIANT, kind,
                f"awaiting trigger: {obligation.get('trigger_event')}",
                None, needs_attention=False)

        if kind == SELF_DECLARED_REVIEW:
            # The guideline states the duty but not the frequency, so nobody has
            # yet decided one. Not late — but not tracked either, and it must not
            # read as a clean record.
            return ObligationStatus(
                COMPLIANT, kind,
                "the guideline sets no frequency — a cadence must be agreed with "
                "the client before this can be tracked",
                None, needs_attention=True)

        # Periodic with no due date has never been scheduled. Reported as
        # overdue on purpose: in a registry whose job is noticing absence, an
        # unscheduled duty must demand attention rather than look satisfied.
        return ObligationStatus(
            OVERDUE, kind,
            "periodic obligation with no next_due_on — never scheduled",
            None, needs_attention=True)

    days = (due - today).days

    if today > due + timedelta(days=grace):
        late = (today - due).days
        return ObligationStatus(
            OVERDUE, kind,
            f"due {due.isoformat()}, {late} day(s) ago"
            + (f", grace of {grace} day(s) exhausted" if grace else ""),
            days, needs_attention=False)

    if days < 0:
        return ObligationStatus(
            DUE_SOON, kind,
            f"due {due.isoformat()}, within {grace}-day grace period",
            days, needs_attention=False)

    if days <= due_soon_window(obligation, default_days):
        return ObligationStatus(
            DUE_SOON, kind, f"due in {days} day(s), on {due.isoformat()}",
            days, needs_attention=False)

    return ObligationStatus(
        COMPLIANT, kind, f"next due {due.isoformat()}", days, needs_attention=False)


def satisfy(obligation: Mapping[str, Any], satisfied_on: date,
            evidence_id: Optional[str] = None,
            evidence_kind: Optional[str] = None) -> dict:
    """The column changes recording that evidence arrived.

    Returns a patch rather than mutating, so the caller decides whether to write
    it and the function stays pure. A periodic obligation gets its next due date;
    an event-triggered one goes back to awaiting its next trigger.

    `evidence_id` and `evidence_kind` are one fact and must be given together.
    023's obligations_satisfied_pair_check rejects half of it, and rightly: a kind
    with no id names a category of evidence nobody can produce, and an id with no
    kind cannot be resolved to a table, since §4.3 makes the reference polymorphic
    across lab_samples, certificates, inspections and risk_assessments with no
    foreign key to disambiguate it. Caught by the database on the first real run
    of this function.
    """
    if bool(evidence_id) != bool(evidence_kind):
        raise ValueError(
            "evidence_id and evidence_kind must be given together or not at all — "
            "023's obligations_satisfied_pair_check rejects a half-recorded "
            f"reference (got id={evidence_id!r}, kind={evidence_kind!r})")

    patch: dict[str, Any] = {
        "last_satisfied_at": satisfied_on.isoformat(),
        "last_satisfied_by": evidence_id or None,
        "last_satisfied_kind": evidence_kind or None,
    }
    nxt = next_due_after(satisfied_on, obligation)
    patch["next_due_on"] = nxt.isoformat() if nxt else None
    return patch


def summarise(obligations, today: date,
              default_days: int = DEFAULT_DUE_SOON_DAYS) -> dict:
    """Counts for a dashboard.

    `needs_attention` is counted separately and NOT folded into overdue. They are
    different conversations: one is "you are late", the other is "we cannot tell
    whether you are late", and merging them would let a configuration gap hide
    inside a compliance figure.
    """
    counts = {s: 0 for s in STATUSES}
    attention = 0
    for ob in obligations:
        result = evaluate(ob, today, default_days)
        counts[result.status] += 1
        if result.needs_attention:
            attention += 1
    counts["needs_attention"] = attention
    counts["total"] = sum(counts[s] for s in STATUSES)
    return counts
