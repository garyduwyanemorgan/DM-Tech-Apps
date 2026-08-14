"""Turning an entitlement into obligations.

§4.5's claim is that ticking a module is simultaneously the onboarding flow, the
billing driver and the scope of what the app monitors. The first two are just
rows. The third needs this: when a client becomes entitled to a module, the
duties that module states must become duties that client is tracked against.

`module_obligations` (027) holds what the guideline says. `obligations` (023)
holds what a particular client owes, on a particular site, with a due date. This
module is the function between them.

Pure — it returns rows for a caller to write, and takes `today` as a parameter
rather than reading the clock, so an onboarding run is reproducible.

THE DECISION THAT MATTERS: WHEN IS THE FIRST ONE DUE
----------------------------------------------------
A client entitled to GU44 today has no Legionella sample on file. Three answers
are possible and only one is honest:

  * `today + cadence` — assumes they have just been sampled. They have not; we
    have no evidence at all. This manufactures a clean record out of nothing and
    is the exact failure §7.4 and the ageing engine are built to prevent.
  * a date the guideline specifies — no guideline specifies one, because the
    guideline does not know when a client signed up.
  * `today` — the duty is outstanding now, because no evidence exists.

So the default is `today`: a newly entitled module starts with its obligations
due, and the client discharges them by uploading evidence. That will look
alarming on day one, and it should — an FM contractor with no Legionella
certificate genuinely is not in a position to prove compliance.

`first_due_on` is a parameter so onboarding can override it per obligation when
the client can show the duty was already discharged before they signed up. That
override should record what it was based on; it is a claim about the past.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Optional

from core.obligations import (
    EVENT_TRIGGERED, PERIODIC, SELF_DECLARED_REVIEW, cadence_kind, evaluate,
)

# Columns copied from the template unchanged. Kept explicit rather than
# spreading the whole row: a template carries provenance (source_page,
# source_quote, confidence) that describes the DOCUMENT, not the client's
# instance, and copying it onto an obligation would misattribute evidence.
_COPIED = ("obligation_type", "label", "cadence_months", "cadence_days",
           "trigger_event", "self_declared_review", "grace_days", "spec_set_id")


def instantiate(template: Mapping[str, Any], entitlement: Mapping[str, Any],
                today: date, *, site_id: Optional[str] = None,
                asset_id: Optional[str] = None,
                first_due_on: Optional[date] = None) -> dict:
    """One obligation row for one client, from one template.

    `entitlement` must carry `id` and `organization_id`. 023's composite foreign
    key checks that pair against organization_entitlements, so passing an
    entitlement belonging to another tenant is rejected by the database rather
    than silently creating a cross-tenant obligation.
    """
    kind = cadence_kind(template)

    row: dict[str, Any] = {
        "organization_id": entitlement["organization_id"],
        "entitlement_id": entitlement["id"],
        "standard_id": template["standard_id"],
        "module_obligation_id": template.get("id"),
        "site_id": site_id,
        "asset_id": asset_id,
    }
    for col in _COPIED:
        if col in template:
            row[col] = template[col]
    row.setdefault("grace_days", 0)
    row.setdefault("self_declared_review", False)

    # Only a periodic duty has a due date at creation. An event-triggered one
    # waits for its event; a self-declared review waits for somebody to agree a
    # cadence. Inventing a date for either would be inventing a deadline.
    if kind == PERIODIC:
        due = first_due_on or today
        row["next_due_on"] = due.isoformat()
    else:
        row["next_due_on"] = None

    # status is NOT NULL with no default in 023, precisely so nobody can create a
    # row asserting 'compliant' before anything has been evaluated. So evaluate
    # it, rather than picking a value.
    row["status"] = evaluate(row, today).status
    return row


def instantiate_all(templates: Iterable[Mapping[str, Any]],
                    entitlement: Mapping[str, Any], today: date, *,
                    site_ids: Iterable[Optional[str]] = (None,),
                    first_due_on: Optional[date] = None) -> list[dict]:
    """Every obligation an entitlement creates, across the sites it covers.

    One row per (template, site). A contractor with eleven sites entitled to GU44
    owes eleven separate sampling duties — a single row would go compliant the
    moment any one site produced a certificate, which is the failure mode the
    whole registry exists to prevent.

    site_ids defaults to (None,) so a site-less obligation — a competency, an
    org-wide policy review — is expressible without a special case.
    """
    sites = list(site_ids) or [None]
    return [
        instantiate(t, entitlement, today, site_id=s, first_due_on=first_due_on)
        for t in templates
        for s in sites
    ]


def plan_summary(rows: Iterable[Mapping[str, Any]], today: date) -> dict:
    """What onboarding is about to create, before it writes anything.

    Onboarding should show this and get a decision. Ticking a module that creates
    forty immediately-overdue duties across eleven sites is a legitimate outcome,
    but it must not be a surprise — and the count of duties with no agreed cadence
    is the number of conversations somebody still has to have.
    """
    rows = list(rows)
    by_kind: dict[str, int] = {}
    needs_cadence = 0
    for row in rows:
        kind = cadence_kind(row)
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if kind == SELF_DECLARED_REVIEW:
            needs_cadence += 1
    return {
        "total": len(rows),
        "by_kind": by_kind,
        "needs_cadence_agreed": needs_cadence,
        "due_immediately": sum(
            1 for r in rows if evaluate(r, today).status in ("due_soon", "overdue")),
        "awaiting_trigger": by_kind.get(EVENT_TRIGGERED, 0),
    }
