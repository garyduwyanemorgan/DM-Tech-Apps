"""Instantiating obligations from an entitlement.

The load-bearing assertion here is that a newly entitled client starts OWING
their duties rather than starting clean. Everything else is bookkeeping.
"""
from __future__ import annotations

from datetime import date

import pytest

from core.entitlements import instantiate, instantiate_all, plan_summary
from core.obligations import EVENT_TRIGGERED, PERIODIC, SELF_DECLARED_REVIEW, evaluate

TODAY = date(2026, 8, 15)
ENT = {"id": "ent-1", "organization_id": "org-1"}


def template(**kw):
    base = {"id": "tpl-1", "standard_id": "std-1", "obligation_type": "sampling",
            "label": "Quarterly sample", "cadence_months": None, "cadence_days": None,
            "trigger_event": None, "self_declared_review": False, "grace_days": 0}
    base.update(kw)
    return base


# ── The decision that matters ────────────────────────────────────────────────

def test_a_new_entitlement_starts_owing_not_clean():
    """No evidence exists, so the duty is outstanding now. Never today+cadence."""
    row = instantiate(template(cadence_months=3), ENT, TODAY)
    assert row["next_due_on"] == "2026-08-15"
    assert evaluate(row, TODAY).status in ("due_soon", "overdue")


def test_first_due_on_can_be_overridden_for_a_duty_already_discharged():
    row = instantiate(template(cadence_months=3), ENT, TODAY,
                      first_due_on=date(2026, 11, 1))
    assert row["next_due_on"] == "2026-11-01"
    assert evaluate(row, TODAY).status == "compliant"


def test_status_is_evaluated_not_assumed():
    """023 made status NOT NULL with no default so nobody could assert compliance."""
    near = instantiate(template(cadence_months=3), ENT, TODAY,
                       first_due_on=date(2026, 8, 20))
    far = instantiate(template(cadence_months=3), ENT, TODAY,
                      first_due_on=date(2027, 1, 1))
    assert near["status"] == "due_soon"
    assert far["status"] == "compliant"


# ── The three kinds instantiate differently ──────────────────────────────────

def test_event_triggered_gets_no_due_date():
    row = instantiate(template(trigger_event="after tank disinfection"), ENT, TODAY)
    assert row["next_due_on"] is None
    r = evaluate(row, TODAY)
    assert r.kind == EVENT_TRIGGERED and r.status == "compliant"
    assert r.needs_attention is False


def test_self_declared_review_gets_no_due_date_and_is_flagged():
    """The guideline states a duty and no frequency — somebody must agree one."""
    row = instantiate(template(self_declared_review=True), ENT, TODAY)
    assert row["next_due_on"] is None
    r = evaluate(row, TODAY)
    assert r.kind == SELF_DECLARED_REVIEW
    assert r.needs_attention is True


def test_periodic_carries_its_cadence_through():
    row = instantiate(template(cadence_months=6, grace_days=14), ENT, TODAY)
    assert row["cadence_months"] == 6 and row["grace_days"] == 14
    assert evaluate(row, TODAY).kind == PERIODIC


# ── Provenance is not copied onto the instance ───────────────────────────────

def test_document_provenance_stays_on_the_template():
    """source_page describes the PDF, not the client's evidence."""
    row = instantiate(template(cadence_months=3, source_page=24,
                               source_quote="q", confidence="high"), ENT, TODAY)
    for col in ("source_page", "source_quote", "confidence"):
        assert col not in row


def test_the_instance_records_which_template_it_came_from():
    row = instantiate(template(cadence_months=3), ENT, TODAY)
    assert row["module_obligation_id"] == "tpl-1"


def test_tenant_identity_comes_from_the_entitlement():
    """023's composite FK checks this pair; never take org from anywhere else."""
    row = instantiate(template(cadence_months=3), ENT, TODAY)
    assert row["organization_id"] == "org-1" and row["entitlement_id"] == "ent-1"


# ── One duty per site ────────────────────────────────────────────────────────

def test_one_obligation_per_site_not_one_in_total():
    """A single row would go compliant the moment ANY site produced evidence."""
    rows = instantiate_all([template(cadence_months=3)], ENT, TODAY,
                           site_ids=["s1", "s2", "s3"])
    assert len(rows) == 3
    assert [r["site_id"] for r in rows] == ["s1", "s2", "s3"]


def test_site_less_obligations_are_expressible():
    """A competency or an org-wide policy review attaches to no site."""
    rows = instantiate_all([template(cadence_months=12, obligation_type="competency")],
                           ENT, TODAY)
    assert len(rows) == 1 and rows[0]["site_id"] is None


def test_templates_multiply_across_sites():
    rows = instantiate_all(
        [template(id="a", cadence_months=3), template(id="b", self_declared_review=True)],
        ENT, TODAY, site_ids=["s1", "s2"])
    assert len(rows) == 4


# ── The plan onboarding should show before writing ───────────────────────────

def test_plan_summary_counts_what_is_about_to_happen():
    rows = instantiate_all(
        [template(id="a", cadence_months=3),
         template(id="b", self_declared_review=True),
         template(id="c", trigger_event="after repair")],
        ENT, TODAY, site_ids=["s1", "s2"])
    s = plan_summary(rows, TODAY)
    assert s["total"] == 6
    assert s["by_kind"][PERIODIC] == 2
    assert s["needs_cadence_agreed"] == 2      # the conversations still to have
    assert s["awaiting_trigger"] == 2
    assert s["due_immediately"] == 2           # periodic ones, due today
