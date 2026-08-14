"""End-to-end: seeded database rows -> core.specs -> verdict.

Every other test of the resolver builds its limits in Python. This one reads them
back out of Postgres, which is the only way to catch the class of bug that lives
in the round trip rather than in the logic: PostgREST rendering NUMERIC as a
string, a boolean arriving as 'f' rather than False, a column the seeder never
wrote, a name that differs between the migration and the dataclass.

Skipped unless a database is configured AND seeded, so a normal `pytest` run is
unaffected. To run it:

    bash scripts/apply_schema.sh --container supabase-db
    python -m db.seed_standards
    python -m pytest tests/test_specs_integration.py -v

Requires the SEEDED lagoon set specifically — this asserts against the ten
COMPLIANCE_LIMITS parameters, so an empty or differently-seeded database skips
rather than fails. A skip here means "not exercised", never "passed".
"""
from __future__ import annotations

import pytest

from core.calculations import check_compliance
from core.constants import COMPLIANCE_LIMITS
from core.specs import NOT_ASSESSED, judge, resolve_limits, spec_set_from_rows

LAGOON_KEY = "lagoon_dm_water"


@pytest.fixture(scope="module")
def seeded_spec_set():
    """The lagoon specification set, read back out of the database."""
    try:
        from db.client import get_client, is_configured
    except ImportError:                                   # pragma: no cover
        pytest.skip("supabase client unavailable")

    if not is_configured():
        pytest.skip("Supabase not configured (SUPABASE_URL / SUPABASE_KEY)")

    client = get_client()
    if client is None:
        pytest.skip("could not create a Supabase client")

    try:
        sets = (client.table("specification_sets").select("*")
                .eq("key", LAGOON_KEY).execute().data or [])
        if not sets:
            pytest.skip(f"{LAGOON_KEY} not seeded — run python -m db.seed_standards")
        rows = (client.table("spec_limits").select("*")
                .eq("spec_set_id", sets[0]["id"]).execute().data or [])
    except Exception as exc:                              # pragma: no cover
        pytest.skip(f"database unreachable: {type(exc).__name__}: {exc}")

    if len(rows) != len(COMPLIANCE_LIMITS):
        pytest.skip(f"expected {len(COMPLIANCE_LIMITS)} limits, found {len(rows)} — "
                    "re-run the seeder")

    return spec_set_from_rows(sets[0], rows)


def test_the_set_round_trips_with_its_scope(seeded_spec_set):
    assert seeded_spec_set.key == LAGOON_KEY
    assert seeded_spec_set.applies_to_scope == "lagoon"
    assert len(seeded_spec_set.limits) == len(COMPLIANCE_LIMITS)


@pytest.mark.parametrize("key", sorted(COMPLIANCE_LIMITS))
def test_parity_at_every_bound_using_database_limits(seeded_spec_set, key):
    """The §5 step-2 parity proof, but with limits that came out of Postgres.

    The in-process test proves BOUND_RULES is faithful. This proves the seeder
    wrote it, the database stored it, and PostgREST returned it, without anything
    being lost or retyped along the way.
    """
    lim = COMPLIANCE_LIMITS[key]
    for bound in (lim.min_val, lim.max_val):
        if bound is None:
            continue
        step = max(abs(bound) * 0.01, 0.001)
        for value in (bound - step, bound, bound + step):
            expected = ("COMPLIANT" if check_compliance(key, value).compliant
                        else "NON_COMPLIANT")
            actual = judge(value, seeded_spec_set, parameter_key=key)
            assert actual == expected, (
                f"{key} at {value}: database limits say {actual}, canonical says "
                f"{expected}. Something was lost between the seeder and here."
            )


# ── Resolution must never default (§7.4, and the assets.scope comment in 019) ──

def test_a_scoped_sampled_asset_resolves(seeded_spec_set):
    asset = {"scope": "lagoon", "asset_class": "sampled"}
    assert resolve_limits(asset, [seeded_spec_set]) is seeded_spec_set


def test_an_unclassified_asset_resolves_to_none(seeded_spec_set):
    """No scope means no verdict. A default here is a confident wrong answer."""
    assert resolve_limits({"asset_class": "sampled"}, [seeded_spec_set]) is None


def test_equipment_does_not_resolve_to_a_sampled_set(seeded_spec_set):
    asset = {"scope": "lagoon", "asset_class": "equipment"}
    assert resolve_limits(asset, [seeded_spec_set]) is None


def test_an_unresolved_asset_yields_not_assessed(seeded_spec_set):
    """The whole point: unresolved must reach the report as NOT_ASSESSED."""
    limits = resolve_limits({"asset_class": "sampled"}, [seeded_spec_set])
    assert judge(7.0, limits, parameter_key="ph") == NOT_ASSESSED


# ── Qualified values: what COMPLIANCE_LIMITS could never express ──────────────

@pytest.mark.parametrize("raw,key,expected", [
    # The whole possible range is below 200, so this is a genuine pass.
    ("<1", "ecoli", "COMPLIANT"),
    ("<1", "total_coliforms", "COMPLIANT"),
    # Never coerced to a measured zero — migration 016 forbids it.
    ("Not Detected", "ecoli", "COMPLIANT"),
    ("250", "ecoli", "NON_COMPLIANT"),
])
def test_qualified_values_against_database_limits(seeded_spec_set, raw, key, expected):
    assert judge(raw, seeded_spec_set, parameter_key=key) == expected
