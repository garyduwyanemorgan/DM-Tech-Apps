"""Ticking a module: the create path is a §7.5 hole unless its inputs are bounded.

§7.5 is normally discussed as the un-tick threat — stop monitoring a duty you are
late on. `POST /entitlements` is the same threat wearing a different hat, and it
is quieter: `first_due_on` flows to `core/entitlements.py:84-88`, which sets
`next_due_on` and hence the status `core/obligations.py` computes. A
`first_due_on` of 2035-01-01 makes every periodic obligation in the module read
`compliant` from creation, with no warning block, no `no_longer_monitored` list,
and (before this work) nothing in the audit record to notice.

Three findings from SECURITY_REVIEW_COMPLIANCE.md are pinned here:

  * **M1** — the audit context now carries the fields that decide whether a duty
    is monitored: active_from, first_due_on, site_ids, price_agreed, confirm.
  * **M2** — a future `first_due_on` is refused with 422, and an override without
    a justification in `notes` is refused too. `active_from` gets a window.
  * **L2** — `price_agreed` and `notes` are bounded at the model, so an oversized
    value is a 422 from pydantic rather than a numeric overflow surfacing as a
    500 (`create_entitlement` propagates exceptions by design).

Style follows tests/test_obligations_api.py: the endpoint function is called
directly with a fake profile and `db.queries` is monkeypatched. No database, no
network, no HTTP layer.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402
import db.queries as queries  # noqa: E402

ORG = "org-1"
SITE_A = "site-a"
SITE_B = "site-b"
TODAY = date.today()
# Long enough to satisfy _OVERRIDE_NOTE_MIN, and shaped like the real thing: a
# claim about evidence that predates the entitlement.
GOOD_NOTE = "Client produced Q2 Legionella certificate dated 2026-05-04."

MODULE = {
    "id": "mod-sellable", "key": "gu44_water_systems", "label": "GU44 Water Systems",
    "category": "water", "standard_id": "std-1", "module_kind": "compliance",
    "obligation_type": "sampling", "status": "available", "provenance": "verified",
    "list_price_monthly": 250, "currency": "AED", "notes": None,
}
TEMPLATES = [
    {"id": "tpl-1", "module_id": "mod-sellable", "standard_id": "std-1",
     "obligation_type": "sampling", "label": "Legionella sampling",
     "cadence_months": 3, "grace_days": 0, "self_declared_review": False},
]


class FakeResponse:
    def __init__(self):
        self.status_code = 200


def _profile(role: str = "super_admin", org: str | None = ORG) -> dict:
    return {"user_id": "clerk-1", "role": role, "organization_id": org, "token": None}


@pytest.fixture
def env(monkeypatch):
    """Returns the state dict; `state["audits"]` collects emitted audit events."""
    state = {"entitlements": [], "inserted": [], "deleted_entitlements": [], "audits": []}

    def list_site_ids(organization_id):
        return [SITE_A, SITE_B] if organization_id == ORG else []

    def get_guideline_module(module_id):
        return MODULE if module_id == MODULE["id"] else None

    def list_module_obligations(module_id):
        return [t for t in TEMPLATES if t["module_id"] == module_id]

    def find_active_entitlement(organization_id, module_id):
        return next((e for e in state["entitlements"]
                     if e["organization_id"] == organization_id
                     and e["module_id"] == module_id
                     and not e.get("active_until")), None)

    def create_entitlement(organization_id, module_id, active_from,
                           price_agreed=None, notes=None):
        row = {"id": "ent-new", "organization_id": organization_id, "module_id": module_id,
               "active_from": active_from, "active_until": None,
               "price_agreed": price_agreed, "notes": notes}
        state["entitlements"].append(row)
        return row

    def insert_obligations(rows):
        state["inserted"].extend(rows)
        return [{**r, "id": f"ob-new-{i}"} for i, r in enumerate(rows)]

    def delete_entitlement_rows(entitlement_id, organization_id):
        state["deleted_entitlements"].append(entitlement_id)

    for name, fn in list(locals().items()):
        if callable(fn) and not name.startswith("_"):
            monkeypatch.setattr(queries, name, fn, raising=True)
    monkeypatch.setattr(api_server, "audit_emit",
                        lambda action, **kw: state["audits"].append((action, kw)))
    return state


def _tick(confirm=True, role="super_admin", org=ORG, active_from=None, **over):
    body = api_server.EntitlementCreate(
        module_id="mod-sellable",
        active_from=active_from or TODAY.isoformat(),
        confirm=confirm, **over)
    response = FakeResponse()
    out = api_server.create_entitlement_endpoint(body, response, profile=_profile(role, org))
    return out, response


# ── M2: first_due_on is a claim about the past, and must behave like one ─────

def test_a_future_first_due_on_is_refused(env):
    """The whole finding: a far-future first_due_on makes the module's entire duty
    set compute `compliant` from creation. Nothing else in the flow objects."""
    with pytest.raises(HTTPException) as exc:
        _tick(first_due_on="2035-01-01", notes=GOOD_NOTE)
    assert exc.value.status_code == 422
    assert "future" in exc.value.detail
    assert env["inserted"] == []
    assert env["entitlements"] == []


def test_even_one_day_in_the_future_is_refused(env):
    """The bound is `> today`, not "obviously absurd" — a month of unmonitored
    time is the same failure at a smaller scale, and there is no honest reason to
    date a first duty forward when no evidence exists for it."""
    with pytest.raises(HTTPException) as exc:
        _tick(first_due_on=(TODAY + timedelta(days=1)).isoformat(), notes=GOOD_NOTE)
    assert exc.value.status_code == 422


def test_a_past_first_due_on_with_a_note_is_accepted(env):
    """The legitimate case must keep working: the duty really was discharged
    before the client signed up, and the note says on what basis."""
    past = TODAY - timedelta(days=30)
    out, _ = _tick(first_due_on=past.isoformat(), notes=GOOD_NOTE)
    assert out["created"] is True
    assert {r["next_due_on"] for r in env["inserted"]} == {past.isoformat()}


def test_first_due_on_without_notes_is_refused(env):
    """No certificate, no sample, no prior obligation row evidences the override —
    the note is the entire audit trail for it."""
    with pytest.raises(HTTPException) as exc:
        _tick(first_due_on=(TODAY - timedelta(days=30)).isoformat())
    assert exc.value.status_code == 422
    assert "notes" in exc.value.detail
    assert env["entitlements"] == []


def test_a_token_note_does_not_satisfy_the_requirement(env):
    with pytest.raises(HTTPException) as exc:
        _tick(first_due_on=(TODAY - timedelta(days=30)).isoformat(), notes="   ok   ")
    assert exc.value.status_code == 422


def test_notes_are_not_required_when_the_default_is_used(env):
    """Only the override is a claim. The default — due today, no evidence on file —
    asserts nothing about the past and needs no justification."""
    out, _ = _tick()
    assert out["created"] is True


def test_an_ancient_first_due_on_is_refused(env):
    with pytest.raises(HTTPException) as exc:
        _tick(first_due_on="1990-01-01", notes=GOOD_NOTE)
    assert exc.value.status_code == 422
    assert "past" in exc.value.detail


# ── M2: active_from gets a window too ────────────────────────────────────────

def test_active_from_far_in_the_future_is_refused(env):
    """023 only checks active_from <= active_until, which bounds neither end. A
    2035 start date is a billing and monitoring window nobody is watching."""
    with pytest.raises(HTTPException) as exc:
        _tick(active_from="2035-01-01")
    assert exc.value.status_code == 422
    assert env["entitlements"] == []


def test_active_from_far_in_the_past_is_refused(env):
    with pytest.raises(HTTPException) as exc:
        _tick(active_from="1990-01-01")
    assert exc.value.status_code == 422


def test_a_modestly_forward_dated_active_from_is_allowed(env):
    """A contract starting next quarter is ordinary commercial reality, and unlike
    first_due_on it does not make anything read as compliant."""
    out, _ = _tick(active_from=(TODAY + timedelta(days=60)).isoformat())
    assert out["created"] is True


def test_a_malformed_date_is_still_a_422_and_says_which_field(env):
    with pytest.raises(HTTPException) as exc:
        _tick(active_from="15/08/2026")
    assert exc.value.status_code == 422
    assert "active_from" in exc.value.detail


# ── L2: bounded price_agreed and notes, so PostgREST never sees them ─────────

def test_an_oversized_price_is_a_422_not_a_500(env):
    """price_agreed is NUMERIC(12,2). create_entitlement propagates exceptions by
    design and the endpoint does not wrap it, so an out-of-range value used to
    reach PostgREST and come back as an unhandled numeric overflow — a 500 for
    what is plainly a bad request. pydantic answers first now."""
    with pytest.raises(ValidationError):
        api_server.EntitlementCreate(module_id="mod-sellable",
                                     active_from=TODAY.isoformat(),
                                     price_agreed=1e15)
    assert env["entitlements"] == []


def test_the_largest_value_the_column_can_hold_is_still_accepted(env):
    out, _ = _tick(price_agreed=9_999_999_999.99)
    assert env["entitlements"][0]["price_agreed"] == 9_999_999_999.99
    assert out["created"] is True


def test_a_negative_price_is_still_refused(env):
    with pytest.raises(ValidationError):
        api_server.EntitlementCreate(module_id="mod-sellable",
                                     active_from=TODAY.isoformat(), price_agreed=-1)


def test_unbounded_notes_are_refused(env):
    with pytest.raises(ValidationError):
        api_server.EntitlementCreate(module_id="mod-sellable",
                                     active_from=TODAY.isoformat(),
                                     notes="x" * 2001)


# ── M1: the audit record carries what decided whether a duty is monitored ────

def _audit(state) -> dict:
    events = [kw for action, kw in state["audits"] if action == "entitlement.create"]
    assert len(events) == 1, state["audits"]
    return events[0]


def test_the_create_audit_carries_the_fields_that_decide_monitoring(env):
    """module_id and a count cannot distinguish "ticked across eleven sites, all
    due now" from "ticked on one site with everything claimed as discharged" —
    and the second is the §7.5 threat arriving through the create path."""
    past = TODAY - timedelta(days=30)
    _tick(first_due_on=past.isoformat(), notes=GOOD_NOTE, site_ids=[SITE_A],
          price_agreed=250.0)
    ctx = _audit(env)
    assert ctx["active_from"] == TODAY.isoformat()
    assert ctx["first_due_on"] == past.isoformat()
    assert ctx["first_due_on_overridden"] is True
    assert ctx["site_ids"] == [SITE_A]
    assert ctx["site_count"] == 1
    assert ctx["all_sites"] is False
    assert ctx["price_agreed"] == 250.0
    assert ctx["notes_provided"] is True
    assert ctx["confirm"] is True
    # The fields that were already there must survive.
    assert ctx["module_id"] == "mod-sellable"
    assert ctx["obligations_created"] == 1


def test_the_audit_records_the_default_case_as_a_non_override(env):
    """The absence of an override is itself worth recording: it is the difference
    between "they had evidence" and "we never asked"."""
    _tick()
    ctx = _audit(env)
    assert ctx["first_due_on"] is None
    assert ctx["first_due_on_overridden"] is False
    assert ctx["notes_provided"] is False
    assert ctx["price_agreed"] is None


def test_omitting_site_ids_is_recorded_as_the_whole_organisation(env):
    """`site_ids: null` means every site in the org — a materially bigger act than
    naming one, and indistinguishable from it in the old record."""
    _tick()
    ctx = _audit(env)
    assert ctx["all_sites"] is True
    assert sorted(ctx["site_ids"]) == [SITE_A, SITE_B]
    assert ctx["site_count"] == 2


def test_the_plan_path_audits_nothing_because_it_writes_nothing(env):
    out, _ = _tick(confirm=False)
    assert out["created"] is False
    assert env["audits"] == []
