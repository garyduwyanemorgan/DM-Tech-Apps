"""The parity proof for the seeded limits.

DM_COMPLIANCE_SCOPING.md §5 step 2 requires that core/specs.py be proved
equivalent to core/calculations.py::check_compliance over a value grid before any
of the seven existing verdict implementations is retired. Half of that proof can
be written now, before the resolver exists: whether the DATA the seeder writes
still describes the behaviour the canonical implementation has today.

That is what this module tests. It never asserts a bound is *correct* against the
published DM guideline — nothing in this repo can, and the seeder says so. It
asserts only that seeding changes no verdict, which is the property that makes
§5 step 1 a non-breaking introduction rather than a silent behaviour change.

The grid deliberately includes each bound EXACTLY. That is the single value where
inclusivity is observable, where the scoping document says the Python and
TypeScript implementations already disagree, and therefore the only place this
test can earn its keep.
"""
from __future__ import annotations

import pytest

from core.calculations import check_compliance
from core.constants import COMPLIANCE_LIMITS
from db.seed_standards import (
    BOUND_RULES, HUMAN_OWNED, SeedError, _guideline_no, _values_differ,
    check_bound_rules, drifted_columns,
)


def judge(value: float, min_val, max_val, min_inclusive: bool, max_inclusive: bool) -> bool:
    """Verdict implied by a seeded spec_limits row.

    The semantics core/specs.py will have to implement. Kept here rather than
    imported so that this test constrains the resolver when it lands, instead of
    agreeing with it by construction.
    """
    if min_val is not None:
        if min_inclusive:
            if value < min_val:
                return False
        elif value <= min_val:
            return False
    if max_val is not None:
        if max_inclusive:
            if value > max_val:
                return False
        elif value >= max_val:
            return False
    return True


def value_grid(lim) -> list[float]:
    """Values around every bound, including the bound itself."""
    values: list[float] = []
    for bound in (lim.min_val, lim.max_val):
        if bound is None:
            continue
        step = max(abs(bound) * 0.01, 0.001)
        values += [bound - step, bound, bound + step]
    if lim.min_val is not None and lim.max_val is not None:
        values.append((lim.min_val + lim.max_val) / 2)
    else:
        anchor = lim.min_val if lim.min_val is not None else lim.max_val
        values += [anchor * 0.5, anchor * 2]
    return values


# ── The parity proof ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(COMPLIANCE_LIMITS))
def test_seeded_bounds_reproduce_check_compliance(key):
    """Seeded strictness must give check_compliance's verdict for every value."""
    lim = COMPLIANCE_LIMITS[key]
    rule = BOUND_RULES[key]

    for value in value_grid(lim):
        expected = check_compliance(key, value).compliant
        actual = judge(value, lim.min_val, lim.max_val,
                       rule.min_inclusive, rule.max_inclusive)
        assert actual == expected, (
            f"{key} at {value}: seeded limits say compliant={actual}, "
            f"check_compliance says {expected}. Seeding this would silently "
            f"change a regulator-facing verdict."
        )


@pytest.mark.parametrize("key", sorted(COMPLIANCE_LIMITS))
def test_verdict_at_the_bound_itself(key):
    """The bound exactly — called out separately because it is the whole point."""
    lim = COMPLIANCE_LIMITS[key]
    rule = BOUND_RULES[key]

    for bound in (lim.min_val, lim.max_val):
        if bound is None:
            continue
        expected = check_compliance(key, bound).compliant
        actual = judge(bound, lim.min_val, lim.max_val,
                       rule.min_inclusive, rule.max_inclusive)
        assert actual == expected, (
            f"{key} at exactly {bound}: seeded={actual}, canonical={expected}."
        )


# ── The fail-closed guard ────────────────────────────────────────────────────

def test_every_limit_has_an_explicit_bound_rule():
    """The seeder must not be able to default a strictness. See 022's comment."""
    assert set(BOUND_RULES) == set(COMPLIANCE_LIMITS)
    check_bound_rules()


def test_check_bound_rules_aborts_on_an_unstated_parameter(monkeypatch):
    """Adding a limit without stating its bounds must stop the seed, not guess."""
    from core.constants import ComplianceLimit
    import db.seed_standards as seeder

    widened = dict(COMPLIANCE_LIMITS)
    widened["nitrate"] = ComplianceLimit("Nitrate", "mg/L", None, 10.0, "< 10")
    monkeypatch.setattr(seeder, "COMPLIANCE_LIMITS", widened)

    with pytest.raises(SeedError, match="nitrate"):
        seeder.check_bound_rules()


def test_check_bound_rules_aborts_on_a_stale_rule(monkeypatch):
    """A rule for a parameter that no longer exists is also a mismatch."""
    import db.seed_standards as seeder

    narrowed = {k: v for k, v in COMPLIANCE_LIMITS.items() if k != "cod"}
    monkeypatch.setattr(seeder, "COMPLIANCE_LIMITS", narrowed)

    with pytest.raises(SeedError, match="cod"):
        seeder.check_bound_rules()


def test_every_bound_rule_states_its_evidence():
    """A strictness with no recorded provenance is a guess wearing a suit."""
    for key, rule in BOUND_RULES.items():
        assert rule.evidence.strip(), f"{key} has no evidence recorded"


def test_qualifier_rules_are_ones_the_migration_permits():
    permitted = {"bound", "detect_fails", "unassessable"}
    for key, rule in BOUND_RULES.items():
        assert rule.qualifier_rule in permitted, f"{key}: {rule.qualifier_rule}"


# ── Drift detection ──────────────────────────────────────────────────────────
#
# These guard the property that makes re-running the seeder safe: it must not
# revert a change a human made in the database, because this seeder's own
# documentation asks for two such changes (linking standard_id, and correcting a
# bound against the published document).

@pytest.mark.parametrize("current,desired,differs", [
    (None, None, False),
    (None, 5.0, True),
    (5.0, None, True),
    (50, 50.0, False),          # PostgREST may render NUMERIC as int or float
    ("50", 50.0, False),        # ...or as a string
    ("50.0000", 50.0, False),
    (50.0, 75.0, True),
    (True, True, False),
    (False, True, True),
    (0, False, False),          # both falsy numerics — not a difference
    ("< 50", "< 50", False),
    ("< 50", "< 75", True),
    ("2025-08-19", "2025-08-19", False),
])
def test_values_differ(current, desired, differs):
    assert _values_differ(current, desired) is differs


def test_human_owned_columns_are_never_reported_as_drift():
    """standard_id is the remediation the docstring asks for — never revert it."""
    current = {"key": "lagoon_dm_water", "standard_id": "a-real-uuid",
               "label": "DM Lagoon Water Quality"}
    desired = {"key": "lagoon_dm_water", "standard_id": None,
               "label": "DM Lagoon Water Quality"}
    assert "standard_id" in HUMAN_OWNED["specification_sets"]
    assert drifted_columns("specification_sets", current, desired) == []


def test_a_changed_bound_is_reported_as_drift():
    """A limit edited in the database must be surfaced, not silently rewritten."""
    current = {"parameter_key": "cod", "max_val": 60, "max_inclusive": True}
    desired = {"parameter_key": "cod", "max_val": 50, "max_inclusive": False}
    assert drifted_columns("spec_limits", current, desired) == [
        "max_inclusive", "max_val",
    ]


def test_supersedes_columns_are_human_owned():
    """Rewriting superseded_issued_on over a linked chain violates 022's CHECK."""
    owned = HUMAN_OWNED["standards"]
    assert {"supersedes_id", "superseded_issued_on"} <= owned
    current = {"code": "DM-HSD-GU44-LCWS2", "supersedes_id": "uuid",
               "superseded_issued_on": None}
    desired = {"code": "DM-HSD-GU44-LCWS2", "supersedes_id": None,
               "superseded_issued_on": "2024-12-17"}
    assert drifted_columns("standards", current, desired) == []


def test_verification_provenance_is_human_owned():
    """--verified-by applies on insert; it must not overwrite a later correction."""
    assert {"verified_by", "verified_on"} <= HUMAN_OWNED["standards"]


# ── Small helpers ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    ("DM-HSD-GU44-LCWS2", 44),
    ("dm-hsd-gu44-lcws2", 44),
    ("DM-HSD-GU7-X", 7),
    ("DM-HSD-NOGUIDELINE", None),
    ("", None),
])
def test_guideline_no_extraction(code, expected):
    assert _guideline_no(code) == expected
