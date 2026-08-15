"""The Obligations API — the registry, the catalogue, and ticking a module.

Phase 1 (§6) promises "an Obligations view (due / due soon / overdue per site)
and a module catalogue with entitlement ticking". These are the endpoints that
make that reachable, and these tests pin the four properties that make them
trustworthy rather than merely present:

  1. **No verdict is computed here.** Every status comes from
     `core.obligations.evaluate`. §5 counts eight divergent verdict
     implementations in this repo already; the tests below assert the endpoint
     agrees with the engine on rows the engine treats specially, so a ninth
     cannot creep in unnoticed.
  2. **`needs_attention` is never folded into `overdue`.** "You are late" and
     "we cannot tell whether you are late" are different conversations, and a
     configuration gap must not be able to hide inside a compliance figure.
  3. **Un-ticking deletes nothing (§7.5).** It closes the entitlement window and
     suspends the obligations. History survives; monitoring is what stops.
  4. **Nothing crosses a tenant boundary.** `obligations` is a map of where a
     contractor is exposed; a row or an entitlement id from another organisation
     must never resolve.

Style follows tests/test_resolver_authz.py: the endpoint functions are called
directly with a fake profile, and `db.queries` is monkeypatched. No database, no
network, no HTTP layer — the endpoints resolve their queries lazily inside the
function body, so patching the module is enough.
"""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402
import db.queries as queries  # noqa: E402
from core.obligations import evaluate  # noqa: E402

TODAY = date(2026, 8, 15)
ORG = "org-1"
OTHER_ORG = "org-2"
SITE_A = "site-a"
SITE_B = "site-b"


def _profile(role: str = "admin", org: str | None = ORG) -> dict:
    return {"user_id": "clerk-1", "role": role, "organization_id": org, "token": None}


class FakeResponse:
    """Stands in for FastAPI's injected Response, which the POST endpoint uses to
    return 201 on the write path and leave 200 on the plan path."""
    def __init__(self):
        self.status_code = 200


# ── Fixtures: a small registry with one of every awkward case ────────────────

def _obligation(**over) -> dict:
    row = {
        "id": "ob-" + over.get("label", "x"),
        "organization_id": ORG,
        "entitlement_id": "ent-1",
        "site_id": SITE_A,
        "label": "quarterly sampling",
        "obligation_type": "sampling",
        "cadence_months": 3,
        "cadence_days": None,
        "trigger_event": None,
        "self_declared_review": False,
        "grace_days": 0,
        "next_due_on": "2026-12-01",
        "status": "compliant",
    }
    row.update(over)
    return row


COMPLIANT = _obligation(label="compliant", next_due_on="2026-12-01")
DUE_SOON = _obligation(label="due_soon", next_due_on="2026-08-20")
OVERDUE = _obligation(label="overdue", next_due_on="2026-06-01")
# Periodic with no due date: never scheduled. The engine calls this overdue AND
# needs_attention — a configuration gap, not a satisfied duty.
UNSCHEDULED = _obligation(label="unscheduled", next_due_on=None)
# The guideline states a duty and no frequency (41 of the loaded corpus). Not
# late, but not tracked either — needs_attention without being overdue.
NO_CADENCE = _obligation(label="no_cadence", cadence_months=None, next_due_on=None,
                         self_declared_review=True, site_id=None)
SUSPENDED = _obligation(label="suspended", next_due_on="2026-01-01", status="suspended")
OTHER_SITE = _obligation(label="other_site", site_id=SITE_B, next_due_on="2026-06-01")

REGISTRY = [COMPLIANT, DUE_SOON, OVERDUE, UNSCHEDULED, NO_CADENCE, SUSPENDED, OTHER_SITE]

MODULE_AVAILABLE = {
    "id": "mod-sellable", "key": "gu44_water_systems", "label": "GU44 Water Systems",
    "category": "water", "standard_id": "std-1", "module_kind": "compliance",
    "obligation_type": "sampling", "status": "available", "provenance": "verified",
    "list_price_monthly": 250, "currency": "AED", "notes": None,
}
MODULE_COMING_SOON = {
    "id": "mod-coming", "key": "gu38_ventilation", "label": "GU38 Ventilation",
    "category": "air", "standard_id": "std-2", "module_kind": "monitoring",
    "obligation_type": None, "status": "coming_soon", "provenance": "unverified",
    "list_price_monthly": None, "currency": "AED", "notes": None,
}
MODULE_UNUSABLE = {
    "id": "mod-unusable", "key": "gu141", "label": "GU141", "category": None,
    "standard_id": "std-3", "module_kind": "unusable", "obligation_type": None,
    "status": "coming_soon", "provenance": "unverified",
    "list_price_monthly": None, "currency": "AED", "notes": None,
}
# A second sellable module, ALREADY entitled. It exists so the pre-seeded
# entitlement does not occupy mod-sellable — otherwise every tick test hits
# "already entitled" by construction and the endpoint's real ordering (404 for an
# unknown module, 409 for one that cannot be sold) is never exercised.
MODULE_ENTITLED = {
    "id": "mod-entitled", "key": "gu81_pools", "label": "GU81 Pools",
    "category": "water", "standard_id": "std-4", "module_kind": "compliance",
    "obligation_type": "sampling", "status": "available", "provenance": "verified",
    "list_price_monthly": 300, "currency": "AED", "notes": None,
}
CATALOGUE = [MODULE_AVAILABLE, MODULE_ENTITLED, MODULE_COMING_SOON, MODULE_UNUSABLE]

TEMPLATES = [
    # The two shapes that matter, both hung off the sellable-and-unticked module:
    # one periodic (due the moment it is created, since no evidence exists yet)
    # and one whose guideline states no frequency at all.
    {"id": "tpl-1", "module_id": "mod-sellable", "standard_id": "std-1",
     "obligation_type": "sampling", "label": "Legionella sampling",
     "cadence_months": 3, "grace_days": 0, "self_declared_review": False},
    {"id": "tpl-2", "module_id": "mod-sellable", "standard_id": "std-1",
     "obligation_type": "review", "label": "written scheme review",
     "self_declared_review": True, "grace_days": 0},
]

ENTITLEMENT = {"id": "ent-1", "organization_id": ORG, "module_id": "mod-entitled",
               "active_from": "2026-01-01", "active_until": None}


@pytest.fixture
def db(monkeypatch):
    """A fake data layer that enforces org scoping the way the real one does:
    every read takes an organization_id and returns nothing for a stranger."""
    state = {
        # Copies, not the module-level rows: suspending an entitlement mutates
        # status in place, and a shared dict would leak that into every later
        # test as a phantom suspension.
        "obligations": [dict(o) for o in REGISTRY],
        "entitlements": [dict(ENTITLEMENT)],
        "inserted": [],
        "deleted_entitlements": [],
        "insert_raises": False,
    }

    def list_obligations(organization_id, site_id=None):
        rows = [o for o in state["obligations"] if o["organization_id"] == organization_id]
        if site_id:
            rows = [o for o in rows if o.get("site_id") == site_id]
        return rows

    def list_site_ids(organization_id):
        return [SITE_A, SITE_B] if organization_id == ORG else []

    def site_names(organization_id):
        return {SITE_A: "Gate Two", SITE_B: "Gate Three"} if organization_id == ORG else {}

    def list_guideline_modules():
        return CATALOGUE

    def get_guideline_module(module_id):
        return next((m for m in CATALOGUE if m["id"] == module_id), None)

    def list_module_obligations(module_id):
        return [t for t in TEMPLATES if t["module_id"] == module_id]

    def list_entitlements(organization_id, active_only=False):
        rows = [e for e in state["entitlements"] if e["organization_id"] == organization_id]
        return [e for e in rows if not e.get("active_until")] if active_only else rows

    def get_entitlement(organization_id, entitlement_id):
        return next((e for e in state["entitlements"]
                     if e["id"] == entitlement_id
                     and e["organization_id"] == organization_id), None)

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
        if state["insert_raises"]:
            raise RuntimeError("obligations_type_check violation")
        state["inserted"].extend(rows)
        return [{**r, "id": f"ob-new-{i}"} for i, r in enumerate(rows)]

    def delete_entitlement_rows(entitlement_id, organization_id):
        state["deleted_entitlements"].append(entitlement_id)
        state["entitlements"] = [e for e in state["entitlements"] if e["id"] != entitlement_id]

    def deactivate_entitlement(organization_id, entitlement_id, active_until):
        ent = get_entitlement(organization_id, entitlement_id)
        if not ent:
            return None
        ent["active_until"] = active_until
        return ent

    def suspend_obligations_for_entitlement(organization_id, entitlement_id):
        n = 0
        for o in state["obligations"]:
            if o["organization_id"] == organization_id and o["entitlement_id"] == entitlement_id:
                o["status"] = "suspended"
                n += 1
        return n

    for name, fn in list(locals().items()):
        if callable(fn) and not name.startswith("_"):
            monkeypatch.setattr(queries, name, fn, raising=True)
    return state


# ── GET /api/obligations ─────────────────────────────────────────────────────

def test_registry_returns_the_org_rows_with_a_computed_verdict(db):
    out = api_server.list_obligations_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    by_label = {o["label"]: o for o in out["obligations"]}
    assert by_label["compliant"]["status"] == "compliant"
    assert by_label["due_soon"]["status"] == "due_soon"
    assert by_label["overdue"]["status"] == "overdue"
    assert by_label["suspended"]["status"] == "suspended"
    assert out["as_of"] == TODAY.isoformat()


def test_every_row_agrees_with_the_engine_exactly(db):
    """The regression guard against a ninth verdict implementation. If anyone
    computes a status in the endpoint or in SQL, this diverges."""
    out = api_server.list_obligations_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    for row, source in zip(out["obligations"], REGISTRY):
        expected = evaluate(source, TODAY)
        assert (row["status"], row["kind"], row["reason"],
                row["days_until_due"], row["needs_attention"]) == tuple(expected)


def test_stored_status_is_reported_but_never_believed(db):
    """A stale `compliant` in the column must not survive contact with the
    ageing engine — that stale value IS the misstatement §4.3 exists to prevent.
    Both are returned so the disagreement is visible rather than papered over."""
    out = api_server.list_obligations_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    overdue = next(o for o in out["obligations"] if o["label"] == "overdue")
    assert overdue["stored_status"] == "compliant"
    assert overdue["status"] == "overdue"


def test_needs_attention_is_reported_separately_and_not_as_overdue(db):
    """NO_CADENCE is a duty with no agreed frequency: it needs attention and is
    NOT late. Folding the two together would report a client as in breach of a
    deadline nobody ever set."""
    out = api_server.list_obligations_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    row = next(o for o in out["obligations"] if o["label"] == "no_cadence")
    assert row["needs_attention"] is True
    assert row["status"] == "compliant"          # not late — nothing was agreed
    summary = out["summary"]
    # UNSCHEDULED (overdue + needs_attention) and NO_CADENCE (needs_attention only)
    assert summary["needs_attention"] == 2
    # OVERDUE, OTHER_SITE (both past their due date) and UNSCHEDULED (periodic,
    # never scheduled). NO_CADENCE is NOT among them: no deadline was ever set,
    # so calling it late would accuse the client of missing one.
    assert summary["overdue"] == 3
    # needs_attention is not a status and must not inflate the total.
    assert summary["total"] == len(REGISTRY)
    assert summary["total"] == (summary["compliant"] + summary["due_soon"]
                                + summary["overdue"] + summary["suspended"])


def test_an_unscheduled_periodic_obligation_is_never_reported_as_clean(db):
    out = api_server.list_obligations_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    row = next(o for o in out["obligations"] if o["label"] == "unscheduled")
    assert row["status"] == "overdue" and row["needs_attention"] is True


def test_as_of_reproduces_an_earlier_reading_of_the_registry(db):
    """An audit re-run must reproduce what the view said on the day, not what it
    would say today."""
    then = api_server.list_obligations_endpoint(as_of="2026-05-01", profile=_profile())
    row = next(o for o in then["obligations"] if o["label"] == "overdue")
    assert row["status"] == "compliant"          # due 2026-06-01, still ahead


def test_as_of_must_be_a_date():
    with pytest.raises(HTTPException) as exc:
        api_server.list_obligations_endpoint(as_of="last tuesday", profile=_profile())
    assert exc.value.status_code == 422


def test_site_filter_narrows_to_that_site(db):
    out = api_server.list_obligations_endpoint(site_id=SITE_B, as_of=TODAY.isoformat(),
                                               profile=_profile())
    assert [o["label"] for o in out["obligations"]] == ["other_site"]
    assert out["obligations"][0]["site_name"] == "Gate Three"


def test_a_site_from_another_tenant_is_not_a_filter_it_is_a_404(db):
    with pytest.raises(HTTPException) as exc:
        api_server.list_obligations_endpoint(site_id="someone-elses-site", profile=_profile())
    assert exc.value.status_code == 404


def test_another_tenants_obligations_are_never_returned(db):
    """The fake data layer scopes by organization_id exactly as the real one
    does; this pins that the endpoint passes its own org and not a caller value."""
    out = api_server.list_obligations_endpoint(profile=_profile(org=OTHER_ORG))
    assert out["obligations"] == []


def test_reading_the_registry_needs_a_permission(db):
    with pytest.raises(HTTPException) as exc:
        api_server.list_obligations_endpoint(profile=_profile(role="pending"))
    assert exc.value.status_code == 403


def test_every_provisioned_role_can_read_the_registry(db):
    for role in ("operator", "admin", "auditor", "super_admin"):
        out = api_server.list_obligations_endpoint(profile=_profile(role=role))
        assert out["obligations"], role


# ── GET /api/obligations/summary ─────────────────────────────────────────────

def test_summary_counts_per_site_and_keeps_needs_attention_separate(db):
    out = api_server.obligations_summary_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    by_site = {s["site_id"]: s for s in out["by_site"]}
    assert set(by_site) == {SITE_A, SITE_B, None}
    assert by_site[SITE_A]["site_name"] == "Gate Two"
    for block in out["by_site"] + [out["totals"]]:
        assert "needs_attention" in block
        assert block["total"] == (block["compliant"] + block["due_soon"]
                                  + block["overdue"] + block["suspended"])


def test_site_less_obligations_are_labelled_not_dropped(db):
    """A competency or an org-wide policy review belongs to nobody's site. Dropping
    it would make the portfolio figure quietly smaller than the truth."""
    out = api_server.obligations_summary_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    org_wide = next(s for s in out["by_site"] if s["site_id"] is None)
    assert org_wide["site_name"] == "Organisation-wide"
    assert org_wide["needs_attention"] == 1
    assert sum(s["total"] for s in out["by_site"]) == out["totals"]["total"]


def test_summary_totals_match_the_engine_run_over_the_same_rows(db):
    from core.obligations import summarise
    out = api_server.obligations_summary_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    assert out["totals"] == summarise(REGISTRY, TODAY)


def test_a_suspended_obligation_counts_as_suspended_never_as_compliant(db):
    """§7.5: un-ticking is commercially correct and must stay visible. A suspended
    duty quietly counted as compliant would turn a commercial decision into a
    clean compliance record."""
    out = api_server.obligations_summary_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    assert out["totals"]["suspended"] == 1


# ── GET /api/modules ─────────────────────────────────────────────────────────

def test_catalogue_marks_this_organisations_entitlements(db):
    out = api_server.list_modules_endpoint(profile=_profile())
    by_id = {m["id"]: m for m in out["modules"]}
    assert by_id["mod-entitled"]["entitled"] is True
    assert by_id["mod-entitled"]["entitlement_id"] == "ent-1"
    # Sellable but never ticked, and coming-soon: neither is entitled, and the
    # two states must not be conflated in the flag.
    assert by_id["mod-sellable"]["entitled"] is False
    assert by_id["mod-coming"]["entitled"] is False
    assert out["entitled_count"] == 1


def test_catalogue_is_global_but_entitlement_is_not(db):
    """Every tenant sees the same catalogue; only the tick differs."""
    mine = api_server.list_modules_endpoint(profile=_profile())
    theirs = api_server.list_modules_endpoint(profile=_profile(org=OTHER_ORG))
    assert len(mine["modules"]) == len(theirs["modules"]) == len(CATALOGUE)
    assert theirs["entitled_count"] == 0


def test_catalogue_carries_kind_status_and_provenance(db):
    out = api_server.list_modules_endpoint(profile=_profile())
    by_id = {m["id"]: m for m in out["modules"]}
    assert by_id["mod-coming"]["module_kind"] == "monitoring"
    assert by_id["mod-coming"]["status"] == "coming_soon"
    assert by_id["mod-coming"]["provenance"] == "unverified"


def test_catalogue_says_why_a_module_cannot_be_ticked(db):
    """A disabled checkbox with no explanation is not an answer. 023 refuses
    status='available' unless provenance='verified', and refuses 'unusable'
    outright — both reasons are stated in words."""
    out = api_server.list_modules_endpoint(profile=_profile())
    by_id = {m["id"]: m for m in out["modules"]}
    assert by_id["mod-sellable"]["sellable"] is True
    assert by_id["mod-sellable"]["not_sellable_reason"] is None
    assert "verified" in by_id["mod-coming"]["not_sellable_reason"]
    assert "contradicts itself" in by_id["mod-unusable"]["not_sellable_reason"]


def test_price_is_hidden_from_roles_that_cannot_see_billing(db):
    operator = api_server.list_modules_endpoint(profile=_profile(role="operator"))
    assert all("list_price_monthly" not in m for m in operator["modules"])
    admin = api_server.list_modules_endpoint(profile=_profile(role="admin"))
    assert any(m.get("list_price_monthly") for m in admin["modules"])


# ── POST /api/entitlements — plan first, then write ──────────────────────────

def _tick(module_id="mod-sellable", confirm=False, role="admin", org=ORG, **over):
    body = api_server.EntitlementCreate(
        module_id=module_id, active_from="2026-08-15", confirm=confirm, **over)
    response = FakeResponse()
    out = api_server.create_entitlement_endpoint(body, response, profile=_profile(role, org))
    return out, response


def test_ticking_without_confirm_returns_a_plan_and_writes_nothing(db):
    out, response = _tick(confirm=False)
    assert out["created"] is False
    assert response.status_code == 200
    assert db["inserted"] == []
    assert len(db["entitlements"]) == 1
    plan = out["plan"]["obligations"]
    # Two templates across two sites = four duties, from one tick.
    assert plan["total"] == 4
    assert plan["needs_cadence_agreed"] == 2
    assert plan["due_immediately"] == 2


def test_the_plan_warns_about_immediately_overdue_duties(db):
    out, _ = _tick(confirm=False)
    assert "due or overdue the moment this is ticked" in out["plan"]["warning"]
    assert "cadence agreed with the client" in out["plan"]["warning"]


def test_confirming_creates_the_entitlement_and_its_obligations(db):
    out, response = _tick(confirm=True)
    assert response.status_code == 201
    assert out["created"] is True
    assert out["entitlement"]["id"] == "ent-new"
    assert out["obligations_created"] == 4
    assert len(db["inserted"]) == 4
    # Every written row is bound to the entitlement that authorises it (§4.5's
    # governing rule) and to the caller's own organisation.
    assert {r["entitlement_id"] for r in db["inserted"]} == {"ent-new"}
    assert {r["organization_id"] for r in db["inserted"]} == {ORG}


def test_written_statuses_come_from_the_engine(db):
    """A periodic duty created today is due today; a duty with no agreed cadence
    has no due date at all. Neither value is chosen by the endpoint."""
    _tick(confirm=True)
    periodic = [r for r in db["inserted"] if r["label"] == "Legionella sampling"]
    review = [r for r in db["inserted"] if r["label"] == "written scheme review"]
    for row in periodic:
        assert row["next_due_on"] == date.today().isoformat()
        assert row["status"] == evaluate(row, date.today()).status
    for row in review:
        assert row["next_due_on"] is None
        assert row["status"] == evaluate(row, date.today()).status


def test_an_unverified_module_is_refused_and_the_refusal_explains_itself(db):
    """023 refuses status='available' unless provenance='verified'. Every module
    currently loaded is coming_soon/unverified, so this path is what a tick
    legitimately does today — and it must read as an editorial gap, not a bug."""
    with pytest.raises(HTTPException) as exc:
        _tick(module_id="mod-coming", confirm=True)
    assert exc.value.status_code == 409
    assert "verified" in exc.value.detail
    assert db["inserted"] == []


def test_an_unusable_guideline_can_never_be_ticked(db):
    with pytest.raises(HTTPException) as exc:
        _tick(module_id="mod-unusable", confirm=True)
    assert exc.value.status_code == 409
    assert "contradicts itself" in exc.value.detail


def test_ticking_an_unknown_module_is_a_404(db):
    with pytest.raises(HTTPException) as exc:
        _tick(module_id="mod-does-not-exist", confirm=True)
    assert exc.value.status_code == 404


def test_ticking_a_module_twice_is_refused(db):
    db["entitlements"].append({"id": "ent-dup", "organization_id": ORG,
                               "module_id": "mod-sellable", "active_from": "2026-01-01",
                               "active_until": None})
    with pytest.raises(HTTPException) as exc:
        _tick(confirm=True)
    assert exc.value.status_code == 409


def test_a_site_from_another_tenant_cannot_be_instantiated_against(db):
    """023's composite foreign key guards the entitlement, not site_id — so this
    check is the only thing standing between a posted id and an obligation row
    hanging off another tenant's site."""
    with pytest.raises(HTTPException) as exc:
        _tick(confirm=True, site_ids=[SITE_A, "site-belonging-to-someone-else"])
    assert exc.value.status_code == 404
    assert db["inserted"] == []


def test_a_failed_obligation_insert_rolls_the_entitlement_back(db):
    """An entitlement with no obligations is a client paying for silence."""
    db["insert_raises"] = True
    with pytest.raises(HTTPException) as exc:
        _tick(confirm=True)
    assert exc.value.status_code == 400
    assert db["deleted_entitlements"] == ["ent-new"]
    assert all(e["id"] != "ent-new" for e in db["entitlements"])


def test_active_from_is_required_and_never_guessed():
    """023 has no DEFAULT on active_from: a guessed date backdates a commercial
    agreement or opens a window of unmonitored time nobody can see."""
    with pytest.raises(Exception):
        api_server.EntitlementCreate(module_id="mod-sellable")


def test_dates_must_be_dates(db):
    body = api_server.EntitlementCreate(module_id="mod-sellable", active_from="15/08/2026")
    with pytest.raises(HTTPException) as exc:
        api_server.create_entitlement_endpoint(body, FakeResponse(), profile=_profile())
    assert exc.value.status_code == 422


def test_operational_roles_cannot_tick_a_module(db):
    for role in ("operator", "auditor", "pending"):
        with pytest.raises(HTTPException) as exc:
            _tick(confirm=True, role=role)
        assert exc.value.status_code == 403, role
    assert db["inserted"] == []


# ── DELETE /api/entitlements/{id} — un-ticking retains everything ────────────

def test_unticking_closes_the_window_and_suspends_without_deleting(db):
    out = api_server.deactivate_entitlement_endpoint("ent-1", active_until="2026-08-31",
                                                     profile=_profile())
    assert out["deactivated"] is True
    assert out["entitlement"]["active_until"] == "2026-08-31"
    assert out["obligations_deleted"] == 0
    # Every obligation is still there, and now visibly suspended.
    assert len(db["obligations"]) == len(REGISTRY)
    assert {o["status"] for o in db["obligations"]} == {"suspended"}
    assert out["obligations_suspended"] == len(REGISTRY)


def test_unticking_names_what_stops_being_monitored(db):
    """§7.5 requires an explicit warning about what stops being tracked. A count
    alone does not tell a client which duty just went dark."""
    out = api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile())
    listed = out["no_longer_monitored"]
    # Every duty is named individually, with the date it was next due — that is
    # what tells a client which gap has just gone dark.
    assert {o["label"] for o in listed} == {o["label"] for o in REGISTRY}
    assert all("id" in o and "next_due_on" in o and "site_id" in o for o in listed)
    assert len(listed) == len(REGISTRY)
    assert "Nothing was deleted" in out["message"]


def test_a_suspended_registry_still_reads_as_suspended_not_compliant(db):
    api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile())
    out = api_server.obligations_summary_endpoint(as_of=TODAY.isoformat(), profile=_profile())
    assert out["totals"]["suspended"] == len(REGISTRY)
    assert out["totals"]["compliant"] == 0


def test_unticking_another_tenants_entitlement_is_a_404(db):
    with pytest.raises(HTTPException) as exc:
        api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile(org=OTHER_ORG))
    assert exc.value.status_code == 404
    assert all(o["status"] != "suspended" or o["label"] == "suspended"
               for o in db["obligations"])


def test_unticking_twice_is_refused(db):
    api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile())
    with pytest.raises(HTTPException) as exc:
        api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile())
    assert exc.value.status_code == 409


def test_the_window_cannot_close_before_it_opened(db):
    with pytest.raises(HTTPException) as exc:
        api_server.deactivate_entitlement_endpoint("ent-1", active_until="2025-01-01",
                                                   profile=_profile())
    assert exc.value.status_code == 422


def test_operational_roles_cannot_untick(db):
    for role in ("operator", "auditor"):
        with pytest.raises(HTTPException) as exc:
            api_server.deactivate_entitlement_endpoint("ent-1", profile=_profile(role=role))
        assert exc.value.status_code == 403, role
