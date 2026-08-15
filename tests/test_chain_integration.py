"""The whole compliance chain, end to end, against real Postgres.

tests/test_specs_integration.py proves one link — seeded limits survive the round
trip into `core.specs`. This proves the chain those limits sit in, which is the
thing the product actually sells (DM_COMPLIANCE_SCOPING.md §4.3, §4.5):

    standard  →  specification set  →  spec limits  →  a verdict
    module    →  entitlement        →  obligations  →  a due date
    ageing    →  satisfaction       →  the next due date

and, underneath all of it, the constraints that stop any of those steps from
lying: 023's cadence CHECK and composite entitlement foreign key, 023's
verified-to-sell and unusable-not-sold CHECKs, 022's spec_limits_bounded_check,
and db/guard.py's refusal to write to the wrong deployment.

NOTHING HERE COMPUTES A VERDICT OR A STATUS. Every verdict comes from
`core.specs.judge` and every status from `core.obligations.evaluate`, with an
explicit `today`. A test that reimplemented either would only prove that two
copies of the same mistake agree — and §5 already counts eight divergent verdict
implementations in this repo without adding a ninth in the test suite.

SKIPPING IS NOT PASSING. Every test below skips when no database is configured,
when the client cannot be built, or when the DM corpus is not loaded — following
the fixture pattern in tests/test_specs_integration.py, so a normal `pytest` run
on a laptop with no Supabase is unaffected. A skip means THIS WAS NOT EXERCISED.
It is never evidence that the chain works. To exercise it:

    bash scripts/apply_schema.sh --container supabase-db     # 000 … 027
    python -m db.load_guidelines
    python -m pytest tests/test_chain_integration.py -v

WHAT THIS TEST TOUCHES. It creates one throwaway organisation named
`zzz-chain-integration-<random>`, entitles it to a module, writes that
entitlement's obligations, and deletes all of it in fixture teardown. It reads
the DM corpus — standards, specification_sets, spec_limits, guideline_modules,
module_obligations — and never writes to it. The two rows it attempts to insert
into guideline_modules are both expected to be REFUSED by a CHECK, so nothing
lands; if one were ever accepted the test fails and the stray row is removed in
teardown.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from core.constants import COMPLIANCE_LIMITS
from core.obligations import (
    COMPLIANT, DUE_SOON, OVERDUE, PERIODIC, add_months, cadence_kind, evaluate,
    satisfy,
)
from core.entitlements import instantiate_all
from core.specs import NOT_ASSESSED, judge, spec_set_from_rows

import core.specs as specs

# Specification sets from the loaded DM corpus. GU81 (public pools) is bounded on
# both sides, GU119 (indoor air) only above — between them they exercise every
# branch of the bound comparison.
GU81_POOL = "gu81_pool_chlorine_le26"
GU81_MICRO = "gu81_microbiological"
GU119_AIR = "gu119_existing_building_long_term"

# The module whose obligations are instantiated. GU119 carries ten templates —
# nine periodic on a range of cadences and one self-declared review — so a single
# entitlement produces all three of the kinds 023/024's cadence CHECK permits.
MODULE_KEY = "gu119"

ORG_PREFIX = "zzz-chain-integration-"

TODAY = date(2026, 6, 1)   # fixed: nothing here may depend on the wall clock


# ── Connecting, and the conditions under which we decline to ─────────────────

def _client_or_skip():
    """The service-role client, or a skip. Same gate as test_specs_integration."""
    try:
        from db.client import get_client, is_configured
    except ImportError:                                   # pragma: no cover
        pytest.skip("supabase client unavailable")

    if not is_configured():
        pytest.skip("Supabase not configured (SUPABASE_URL / SUPABASE_KEY)")

    client = get_client()
    if client is None:
        pytest.skip("could not create a Supabase client")
    return client


@pytest.fixture(scope="module")
def client():
    c = _client_or_skip()
    # Probe the two tables the whole file depends on. An unapplied 022/023 is a
    # skip, not a failure — the schema is not this test's job to create.
    for table in ("spec_limits", "obligations", "module_obligations"):
        try:
            c.table(table).select("id").limit(1).execute()
        except Exception as exc:
            pytest.skip(f"{table} unreadable — apply migrations 000–027 "
                        f"({type(exc).__name__}: {exc})")
    return c


@pytest.fixture(scope="module")
def spec_sets(client):
    """The three DM specification sets this file judges against, from Postgres.

    Built through core.specs.spec_set_from_rows, so a column the loader never
    wrote, a NUMERIC rendered as a string, or a NULL min_inclusive shows up here
    as a SpecError rather than as a quietly wrong verdict downstream.
    """
    out = {}
    for key in (GU81_POOL, GU81_MICRO, GU119_AIR):
        try:
            sets = (client.table("specification_sets").select("*")
                    .eq("key", key).is_("organization_id", "null")
                    .execute().data or [])
        except Exception as exc:                          # pragma: no cover
            pytest.skip(f"database unreachable: {type(exc).__name__}: {exc}")
        if not sets:
            pytest.skip(f"{key} not loaded — run python -m db.load_guidelines")
        rows = (client.table("spec_limits").select("*")
                .eq("spec_set_id", sets[0]["id"]).execute().data or [])
        if not rows:
            pytest.skip(f"{key} has no spec_limits — the corpus is half loaded")
        out[key] = spec_set_from_rows(sets[0], rows)
    return out


@pytest.fixture(scope="module")
def tenant(client):
    """A throwaway organisation entitled to one module, with its obligations.

    Everything created here is deleted in teardown, in dependency order:
    obligations reference the entitlement ON DELETE RESTRICT (§7.5), so they go
    first, and the organisation last. The DM corpus is never written to.
    """
    modules = (client.table("guideline_modules").select("*")
               .eq("key", MODULE_KEY).execute().data or [])
    if not modules:
        pytest.skip(f"module {MODULE_KEY} not loaded — the catalogue is empty")
    module = modules[0]

    templates = (client.table("module_obligations").select("*")
                 .eq("module_id", module["id"]).execute().data or [])
    if not templates:
        pytest.skip(f"{MODULE_KEY} states no module_obligations — 027 not loaded")

    name = ORG_PREFIX + uuid.uuid4().hex[:12]
    org = client.table("organizations").insert(
        {"name": name, "plan_name": "starter", "site_limit": 1}).execute().data[0]

    state = {"org": org, "module": module, "templates": templates,
             "entitlement": None, "obligations": [], "spec_set_id": None}
    try:
        # Writes from here on are DELIBERATELY unguarded. An RLS refusal against
        # the service-role key is a real finding about the schema and must fail
        # this fixture loudly rather than be turned into a skip.
        state["entitlement"] = client.table("organization_entitlements").insert({
            "organization_id": org["id"],
            "module_id": module["id"],
            "active_from": TODAY.isoformat(),
        }).execute().data[0]

        rows = instantiate_all(templates, state["entitlement"], TODAY)
        state["planned"] = rows
        state["obligations"] = (client.table("obligations")
                                .insert(rows).execute().data or [])
        yield state
    finally:
        _cleanup(client, org["id"], state)


def _cleanup(client, org_id: str, state: dict) -> None:
    client.table("obligations").delete().eq("organization_id", org_id).execute()
    client.table("spec_limits").delete().eq(
        "spec_set_id", state.get("spec_set_id") or uuid.UUID(int=0).hex).execute() \
        if state.get("spec_set_id") else None
    if state.get("spec_set_id"):
        client.table("specification_sets").delete().eq(
            "id", state["spec_set_id"]).execute()
    client.table("organization_entitlements").delete().eq(
        "organization_id", org_id).execute()
    # Any module row a CHECK was expected to refuse but did not.
    client.table("guideline_modules").delete().like("key", "zzz-chain-%").execute()
    client.table("organizations").delete().eq("id", org_id).execute()


# ── 1. Standards → specification sets → limits → verdict ─────────────────────

def test_the_pool_set_carries_its_scope_and_limits(spec_sets):
    """The set arrived whole: key, scope and a non-trivial number of limits."""
    pool = spec_sets[GU81_POOL]
    assert pool.key == GU81_POOL
    assert pool.applies_to_scope == "facilities"
    assert pool.organization_id is None, "a built-in set must not be org-scoped"
    assert pool.standard_id, "limits attributed to no standard cannot be cited (§7.1)"
    assert len(pool.limits) >= 4


def test_the_air_set_carries_its_scope_and_limits(spec_sets):
    air = spec_sets[GU119_AIR]
    assert air.applies_to_scope == "facilities"
    assert air.standard_id
    assert len(air.limits) >= 8


@pytest.mark.parametrize("set_key,parameter_key", [
    (GU81_POOL, "ph"),
    (GU81_POOL, "free_chlorine"),
    (GU81_POOL, "total_alkalinity"),
    (GU81_POOL, "cyanuric_acid"),
    (GU119_AIR, "co2_8_hour"),
    (GU119_AIR, "formaldehyde_8_hour"),
    (GU119_AIR, "pm2_5_24_hour"),
    (GU119_AIR, "total_bacterial_counts"),
])
def test_verdict_at_every_bound_of_a_database_limit(spec_sets, set_key, parameter_key):
    """Judge just under, exactly on, and just over each published bound.

    The verdict comes from core.specs.judge; this test only says which side of
    the boundary each value falls, which is arithmetic on the stored bound and
    not a second implementation of the rule. Strictness comes from
    min_inclusive/max_inclusive as 022 stored them — never from `display`.
    """
    spec = spec_sets[set_key]
    limit = spec.limit_for(parameter_key)
    if limit is None:
        pytest.skip(f"{set_key} does not judge {parameter_key} in this corpus")

    def step(bound: float) -> float:
        return max(abs(bound) * 0.01, 0.001)

    if limit.min_val is not None:
        lo = limit.min_val
        assert judge(lo - step(lo), spec, parameter_key=parameter_key) == "NON_COMPLIANT"
        on_bound = judge(lo, spec, parameter_key=parameter_key)
        assert on_bound == ("COMPLIANT" if limit.min_inclusive else "NON_COMPLIANT"), (
            f"{parameter_key} exactly on its lower bound {lo}: min_inclusive is "
            f"{limit.min_inclusive} in the database, judge said {on_bound}")
        if limit.max_val is None or lo + step(lo) <= limit.max_val:
            assert judge(lo + step(lo), spec, parameter_key=parameter_key) == "COMPLIANT"

    if limit.max_val is not None:
        hi = limit.max_val
        assert judge(hi + step(hi), spec, parameter_key=parameter_key) == "NON_COMPLIANT"
        on_bound = judge(hi, spec, parameter_key=parameter_key)
        assert on_bound == ("COMPLIANT" if limit.max_inclusive else "NON_COMPLIANT"), (
            f"{parameter_key} exactly on its upper bound {hi}: max_inclusive is "
            f"{limit.max_inclusive} in the database, judge said {on_bound}")


def test_these_limits_came_from_the_database_not_from_python(spec_sets):
    """The point of the whole migration: limits are DATA, not core/constants.py.

    A pool pH of 7.0 is COMPLIANT against the lagoon dict (6.0–9.0) and
    NON-COMPLIANT against GU81 (7.2–7.6). If the resolver were still reaching
    for COMPLIANCE_LIMITS, this assertion is the one that would notice.
    """
    pool = spec_sets[GU81_POOL]

    assert COMPLIANCE_LIMITS["ph"].min_val == 6.0 and COMPLIANCE_LIMITS["ph"].max_val == 9.0
    assert pool.limit_for("ph").min_val != COMPLIANCE_LIMITS["ph"].min_val
    assert judge(7.0, pool, parameter_key="ph") == "NON_COMPLIANT"

    # Parameters the Python dict has never heard of, judged anyway.
    for unknown in ("free_chlorine", "cyanuric_acid", "total_alkalinity"):
        assert unknown not in COMPLIANCE_LIMITS
        assert pool.limit_for(unknown) is not None

    air = spec_sets[GU119_AIR]
    assert "co2_8_hour" not in COMPLIANCE_LIMITS
    assert judge(2000, air, parameter_key="co2_8_hour") == "NON_COMPLIANT"


def test_a_parameter_the_set_does_not_judge_is_not_assessed(spec_sets):
    """A partial set leaves the rest unassessed — never a default, never a pass."""
    assert spec_sets[GU81_POOL].limit_for("legionella_pneumophila") is None
    assert judge(500, spec_sets[GU81_POOL],
                 parameter_key="legionella_pneumophila") == NOT_ASSESSED


def test_qualified_results_follow_the_rule_stored_on_the_limit(spec_sets):
    """qualifier_rule as 022 stored it, not as the test assumes.

    GU81's microbiological limits are `detect_fails` — the printed requirement is
    zero — so a non-detection passes and any quantified value fails. Nothing is
    coerced to a measured 0.0 anywhere (migration 016).
    """
    micro = spec_sets[GU81_MICRO]
    coliforms = micro.limit_for("total_coliforms")
    if coliforms is None:
        pytest.skip("GU81 microbiological set does not carry total_coliforms")

    assert coliforms.qualifier_rule == specs.RULE_DETECT_FAILS
    assert judge("Not Detected", micro, parameter_key="total_coliforms") == "COMPLIANT"
    assert judge("<1", micro, parameter_key="total_coliforms") == "COMPLIANT"
    assert judge("5", micro, parameter_key="total_coliforms") == "NON_COMPLIANT"


# ── 2. Templates → entitlement → obligations ─────────────────────────────────

def test_ticking_a_module_creates_one_obligation_per_template(tenant):
    """§4.5: ticking a module IS the act of creating the monitoring scope."""
    assert len(tenant["obligations"]) == len(tenant["templates"]), (
        "an entitlement must produce every duty its module states — a template "
        "that silently fails to instantiate is a duty nobody is tracking")


def test_every_written_obligation_is_tied_to_its_entitlement_and_tenant(tenant):
    ent = tenant["entitlement"]
    for row in tenant["obligations"]:
        assert row["entitlement_id"] == ent["id"]
        assert row["organization_id"] == ent["organization_id"]
        assert row["standard_id"], "an obligation citing no standard is uncitable"


def test_instances_remember_the_template_they_came_from(tenant):
    """027's module_obligation_id — what makes a later edition diffable."""
    template_ids = {t["id"] for t in tenant["templates"]}
    linked = [r for r in tenant["obligations"] if r.get("module_obligation_id")]
    assert len(linked) == len(tenant["obligations"])
    assert {r["module_obligation_id"] for r in linked} == template_ids


def test_a_self_declared_review_lands_with_no_due_date(tenant):
    """41 corpus obligations state a duty and no frequency. Inventing a deadline
    for them would be inventing an agreement (§4.3, 027's column comment)."""
    reviews = [r for r in tenant["obligations"] if r.get("self_declared_review")]
    if not reviews:
        pytest.skip(f"{MODULE_KEY} states no self-declared review in this corpus")
    for row in reviews:
        assert row["next_due_on"] is None
        result = evaluate(row, TODAY)
        assert result.needs_attention is True, (
            "a duty with no agreed cadence must demand a conversation, not read "
            "as a clean record")


def test_periodic_obligations_land_due_immediately(tenant):
    """A newly entitled client has no evidence on file, so the duty is
    outstanding now. Alarming on day one, and correct (core/entitlements.py)."""
    periodic = [r for r in tenant["obligations"]
                if cadence_kind(r) == PERIODIC]
    assert periodic, "GU119 states periodic duties; none were instantiated"
    for row in periodic:
        assert row["next_due_on"] == TODAY.isoformat()
        assert evaluate(row, TODAY).status in (DUE_SOON, OVERDUE)


def test_the_stored_status_is_the_one_evaluate_produced(tenant):
    """023 gave `status` no DEFAULT so nobody could assert a clean record before
    anything was evaluated. Confirm the value in Postgres is evaluate's."""
    for row in tenant["obligations"]:
        assert row["status"] == evaluate(row, TODAY).status


def test_obligations_read_back_through_the_query_layer(client, tenant):
    """db.queries.list_obligations sees exactly what was written, and nothing
    from any other tenant."""
    from db.queries import list_obligations
    rows = list_obligations(tenant["org"]["id"])
    assert len(rows) == len(tenant["obligations"])
    assert {r["organization_id"] for r in rows} == {tenant["org"]["id"]}


# ── 3. Ageing over time ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def aged_obligation(client, tenant):
    """One periodic obligation, given a fixed due date and a real grace window.

    Both are set on the CLIENT'S OWN row, never on the corpus template: 027 says
    outright that a client needing a different cadence changes it on their own
    obligation. grace_days is moved off 0 because a zero grace makes the
    in-grace branch of evaluate unreachable, and it is a branch that decides
    whether a client is told they are late.
    """
    candidates = [r for r in tenant["obligations"] if r.get("cadence_months")]
    if not candidates:
        pytest.skip("no month-cadenced obligation to age")
    row = max(candidates, key=lambda r: r["cadence_months"])
    updated = (client.table("obligations")
               .update({"next_due_on": "2026-09-01", "grace_days": 14})
               .eq("id", row["id"]).execute().data[0])
    # Re-read rather than trust the update's echo: next_due_on comes back as a
    # string, and evaluate parsing it is part of what this exercises.
    return (client.table("obligations").select("*")
            .eq("id", updated["id"]).execute().data[0])


def test_the_aged_row_is_periodic_and_kept_its_dates(aged_obligation):
    assert cadence_kind(aged_obligation) == PERIODIC
    assert aged_obligation["next_due_on"] == "2026-09-01"
    assert aged_obligation["grace_days"] == 14


@pytest.mark.parametrize("today,expected,why", [
    (date(2026, 6, 1), COMPLIANT, "three months out, well beyond the warning window"),
    (date(2026, 8, 25), DUE_SOON, "seven days before the due date"),
    (date(2026, 9, 1), DUE_SOON, "on the due date itself, not yet late"),
    (date(2026, 9, 10), DUE_SOON, "nine days past due, inside the 14-day grace"),
    (date(2026, 9, 16), OVERDUE, "grace exhausted the day before"),
    (date(2027, 3, 1), OVERDUE, "half a year late"),
])
def test_status_at_a_given_date(aged_obligation, today, expected, why):
    """The status is core.obligations.evaluate's, computed against an explicit
    `today` so re-running an audit next year reproduces this year's answer."""
    result = evaluate(aged_obligation, today)
    assert result.status == expected, f"{today}: expected {expected} ({why}), " \
                                      f"got {result.status} — {result.reason}"
    assert result.needs_attention is False, "a scheduled duty is not a data gap"


def test_days_until_due_goes_negative_after_the_due_date(aged_obligation):
    assert evaluate(aged_obligation, date(2026, 8, 25)).days_until_due == 7
    assert evaluate(aged_obligation, date(2026, 9, 10)).days_until_due == -9


# ── 4. Satisfaction ──────────────────────────────────────────────────────────

def test_satisfying_an_obligation_reschedules_it(client, tenant):
    """Evidence arrives: write core.obligations.satisfy's patch, read it back.

    The next due date is measured from the date the duty was SATISFIED, not from
    the date it was due — measuring from the due date would stack a second
    deadline on a breach the client is already dealing with.
    """
    candidates = [r for r in tenant["obligations"]
                  if r.get("cadence_months") and r["id"] != _aged_id(tenant)]
    if not candidates:
        pytest.skip("no second month-cadenced obligation to satisfy")
    row = min(candidates, key=lambda r: r["cadence_months"])

    satisfied_on = date(2026, 8, 15)
    evidence_id = str(uuid.uuid4())
    patch = satisfy(row, satisfied_on, evidence_id=evidence_id,
                    evidence_kind="lab_sample")
    merged = {**row, **patch}
    patch["status"] = evaluate(merged, satisfied_on).status

    client.table("obligations").update(patch).eq("id", row["id"]).execute()
    stored = (client.table("obligations").select("*")
              .eq("id", row["id"]).execute().data[0])

    expected_due = add_months(satisfied_on, row["cadence_months"])
    assert stored["next_due_on"] == expected_due.isoformat()
    assert stored["last_satisfied_by"] == evidence_id
    assert stored["last_satisfied_kind"] == "lab_sample"
    assert stored["last_satisfied_at"] is not None

    # And the status the database now holds is still evaluate's, re-derived from
    # the row Postgres returned rather than from the one we sent.
    assert stored["status"] == evaluate(stored, satisfied_on).status
    assert evaluate(stored, satisfied_on).status == COMPLIANT
    assert evaluate(stored, expected_due).status == DUE_SOON
    assert evaluate(stored, add_months(expected_due, 1)).status == OVERDUE


def _aged_id(tenant) -> str:
    """The row test_status_at_a_given_date owns, so satisfaction picks another."""
    monthly = [r for r in tenant["obligations"] if r.get("cadence_months")]
    return max(monthly, key=lambda r: r["cadence_months"])["id"] if monthly else ""


def test_half_a_satisfaction_record_is_refused_before_it_reaches_the_database(tenant):
    """core.obligations.satisfy refuses what 023's satisfied_pair_check refuses:
    an evidence id with no table name cannot be resolved by anybody."""
    row = tenant["obligations"][0]
    with pytest.raises(ValueError):
        satisfy(row, date(2026, 8, 15), evidence_id=str(uuid.uuid4()))
    with pytest.raises(ValueError):
        satisfy(row, date(2026, 8, 15), evidence_kind="lab_sample")


# ── 5. The constraints compliance integrity rests on ─────────────────────────
#
# These are guarantees, not implementation details: each one is the database
# refusing a row that would make the registry quietly wrong. They are pinned here
# so that a future migration cannot drop one without something going red.

def _refused(fn) -> str:
    """Run a write that must fail, and return the message. Fails if it lands."""
    try:
        fn()
    except Exception as exc:
        return str(exc)
    pytest.fail("the database ACCEPTED a row it must refuse")


def test_an_obligation_with_neither_cadence_nor_trigger_is_refused(client, tenant):
    """023's obligations_cadence_check. Such a row sits in the registry forever,
    never becoming due and never alerting anyone — the silent gap the whole
    table exists to eliminate, reproduced inside the fix for it."""
    ent = tenant["entitlement"]
    msg = _refused(lambda: client.table("obligations").insert({
        "organization_id": ent["organization_id"],
        "entitlement_id": ent["id"],
        "standard_id": tenant["templates"][0]["standard_id"],
        "obligation_type": "sampling",
        "label": "no cadence, no trigger, no review",
        "status": OVERDUE,
        "self_declared_review": False,
    }).execute())
    assert "obligations_cadence_check" in msg


def test_an_obligation_cannot_borrow_another_tenants_entitlement(client, tenant):
    """023's composite foreign key (entitlement_id, organization_id). A plain FK
    would let org A's obligation hang off org B's entitlement, making the billing
    driver and the monitoring scope disagree while every row looked valid."""
    other = client.table("organizations").insert(
        {"name": ORG_PREFIX + "other-" + uuid.uuid4().hex[:8],
         "plan_name": "starter", "site_limit": 1}).execute().data[0]
    try:
        msg = _refused(lambda: client.table("obligations").insert({
            "organization_id": other["id"],                     # a different tenant
            "entitlement_id": tenant["entitlement"]["id"],      # this tenant's
            "standard_id": tenant["templates"][0]["standard_id"],
            "obligation_type": "sampling",
            "label": "cross-tenant obligation",
            "cadence_months": 3,
            "status": OVERDUE,
        }).execute())
        assert "obligations_entitlement_fk" in msg
    finally:
        client.table("organizations").delete().eq("id", other["id"]).execute()


def test_an_unverified_module_cannot_be_put_on_sale(client, tenant):
    """023's guideline_modules_verified_to_sell_check (§7.1, decision 5). Under
    per-guideline pricing every module is a SKU, so a wrong limit in a sold
    module is a liability rather than a bug — nothing goes on sale until
    somebody has read the published DM PDF."""
    standard_id = tenant["templates"][0]["standard_id"]
    msg = _refused(lambda: client.table("guideline_modules").insert({
        "standard_id": standard_id,
        "key": "zzz-chain-unverified-" + uuid.uuid4().hex[:8],
        "label": "unverified but on sale",
        "module_kind": "compliance",
        "status": "available",
        "provenance": "unverified",
    }).execute())
    assert "guideline_modules_verified_to_sell_check" in msg


def test_an_unusable_module_cannot_be_sold_at_all(client, tenant):
    """023's guideline_modules_unusable_not_sold_check. GU141 contradicts itself;
    there is nothing to deliver and nothing a report could truthfully say, so
    verified provenance does not rescue it."""
    standard_id = tenant["templates"][0]["standard_id"]
    msg = _refused(lambda: client.table("guideline_modules").insert({
        "standard_id": standard_id,
        "key": "zzz-chain-unusable-" + uuid.uuid4().hex[:8],
        "label": "unusable but on sale",
        "module_kind": "unusable",
        "status": "available",
        "provenance": "verified",
    }).execute())
    assert "guideline_modules_unusable_not_sold_check" in msg


def test_a_limit_bounded_on_neither_side_is_refused(client, tenant):
    """022's spec_limits_bounded_check, and core.specs.SpecLimit's own guard.

    Such a limit judges nothing and would silently PASS every value put to it —
    the most dangerous shape a compliance row can take, because it produces
    confident green output from no rule at all. Written against a set owned by
    the throwaway organisation so the DM corpus is untouched.
    """
    org_id = tenant["org"]["id"]
    spec_set = client.table("specification_sets").insert({
        "organization_id": org_id,
        "key": "zzz-chain-unbounded",
        "label": "unbounded probe",
        "applies_to_scope": "facilities",
    }).execute().data[0]
    tenant["spec_set_id"] = spec_set["id"]

    msg = _refused(lambda: client.table("spec_limits").insert({
        "spec_set_id": spec_set["id"],
        "parameter_key": "unbounded",
        "parameter_label": "Unbounded",
        "min_val": None,
        "max_val": None,
        "min_inclusive": True,
        "max_inclusive": True,
        "display": "-",
    }).execute())
    assert "spec_limits_bounded_check" in msg

    # The same refusal in Python, so neither layer is the only thing standing
    # between a nonsense row and a green report.
    with pytest.raises(specs.SpecError):
        specs.spec_limit_from_row({
            "parameter_key": "unbounded", "parameter_label": "Unbounded",
            "min_val": None, "max_val": None,
            "min_inclusive": True, "max_inclusive": True, "display": "-",
        })


# ── 6. The deployment guard ──────────────────────────────────────────────────

def test_the_guard_passes_against_this_database(client):
    """db/guard.py: this database must identify as dm-tech-apps before anything
    in this repo writes to it. The lagoon project carries no such row."""
    from db.guard import EXPECTED_DEPLOYMENT, assert_deployment, read_deployment
    assert read_deployment(client) == EXPECTED_DEPLOYMENT
    assert_deployment(client)          # must not raise


def test_the_guard_refuses_a_different_deployment_name(client):
    """Fail-closed: a database identifying as anything else is a refusal, with
    the SUPABASE_URL hint the operator needs."""
    from db.guard import WrongDatabase, assert_deployment
    with pytest.raises(WrongDatabase) as exc:
        assert_deployment(client, expected="decca-lagoons")
    assert "decca-lagoons" in str(exc.value)
    assert "SUPABASE_URL" in str(exc.value)
