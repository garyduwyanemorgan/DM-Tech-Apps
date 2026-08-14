"""The parity proof for core/specs.py.

DM_COMPLIANCE_SCOPING.md §5 step 2 requires the resolver be proved equivalent to
core/calculations.py::check_compliance — named there as the canonical one of the
eight verdict implementations that currently exist — over a value grid covering
all ten COMPLIANCE_LIMITS parameters, **at exactly the bound**. That is the only
value where inclusivity is observable, and the §5 step-2 note records that the
Python and TypeScript implementations already disagree there for nine of the ten.
Until this passes, no copy may be retired.

The data is the seeded data: db.seed_standards.BOUND_RULES supplies the
strictness COMPLIANCE_LIMITS cannot express, exactly as the seeder writes it into
spec_limits. So this proves the pair (seeded rows, resolver) reproduces today's
verdicts — not that the resolver agrees with some other reading of the same
numbers.

tests/test_seed_standards.py proves the other half — that the seeded DATA still
describes the canonical behaviour — with its own `judge` helper written before
this module existed so that it constrains the resolver rather than agreeing with
it by construction. The semantics here must match that helper; the parity test
below is checked against check_compliance directly, which is the stronger claim.
"""
from __future__ import annotations

import pytest

from core.calculations import check_compliance
from core.constants import COMPLIANCE_LIMITS
from core.specs import (
    COMPLIANT, NON_COMPLIANT, NOT_ASSESSED, SpecError, SpecLimit, SpecSet,
    judge, resolve_limits, spec_limit_from_row, spec_set_from_rows,
)
from db.seed_standards import BOUND_RULES, LAGOON_SET_KEY


# ── The seeded lagoon set, built exactly as db/seed_standards.py writes it ────

def seeded_limit(key: str) -> SpecLimit:
    """One spec_limits row as upsert_spec_limits would insert it."""
    lim = COMPLIANCE_LIMITS[key]
    rule = BOUND_RULES[key]
    return spec_limit_from_row({
        "parameter_key": key,
        "parameter_label": lim.parameter,
        "unit": lim.unit,
        "min_val": lim.min_val,
        "max_val": lim.max_val,
        "min_inclusive": rule.min_inclusive,
        "max_inclusive": rule.max_inclusive,
        "display": lim.display,
        "qualifier_rule": rule.qualifier_rule,
    })


def seeded_lagoon_set(**overrides) -> SpecSet:
    row = {"key": LAGOON_SET_KEY, "label": "DM Lagoon Water Quality",
           "applies_to_scope": "lagoon", "organization_id": None,
           "standard_id": None}
    row.update(overrides)
    return SpecSet(
        key=row["key"], label=row["label"],
        applies_to_scope=row["applies_to_scope"],
        organization_id=row["organization_id"], standard_id=row["standard_id"],
        limits={k: seeded_limit(k) for k in COMPLIANCE_LIMITS},
    )


LAGOON = seeded_lagoon_set()


def value_grid(lim) -> list[float]:
    """Values around every bound, including the bound itself.

    Same construction as tests/test_seed_standards.py::value_grid, deliberately:
    the two halves of the proof must cover the same values or they do not compose.
    """
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


# ── Parity ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(COMPLIANCE_LIMITS))
def test_judge_reproduces_check_compliance(key):
    """The resolver's verdict must equal the canonical one for every value."""
    lim = COMPLIANCE_LIMITS[key]
    for value in value_grid(lim):
        expected = COMPLIANT if check_compliance(key, value).compliant else NON_COMPLIANT
        actual = judge(value, LAGOON, parameter_key=key)
        assert actual == expected, (
            f"{key} at {value}: specs.judge says {actual}, check_compliance says "
            f"{expected}. Retiring a copy behind this test would silently change "
            f"a regulator-facing verdict."
        )


@pytest.mark.parametrize("key", sorted(COMPLIANCE_LIMITS))
def test_parity_at_exactly_the_bound(key):
    """The bound itself — the only value where inclusivity is observable."""
    lim = COMPLIANCE_LIMITS[key]
    for bound in (lim.min_val, lim.max_val):
        if bound is None:
            continue
        expected = COMPLIANT if check_compliance(key, bound).compliant else NON_COMPLIANT
        assert judge(bound, LAGOON, parameter_key=key) == expected, (
            f"{key} at exactly {bound}: specs.judge disagrees with the canonical "
            f"implementation, which says compliant={expected == COMPLIANT}."
        )


def test_the_bound_cases_are_actually_exercised():
    """Guard against a grid that never lands on a bound and proves nothing."""
    bounds = [b for lim in COMPLIANCE_LIMITS.values()
              for b in (lim.min_val, lim.max_val) if b is not None]
    assert len(bounds) == 11        # pH has two; the other nine have one each
    # And the divergence the scoping note describes must be real: on nine of the
    # ten, the bound itself is a breach. If this ever passes trivially, parity is
    # no longer testing anything.
    strict = [k for k, lim in COMPLIANCE_LIMITS.items()
              for b in (lim.min_val, lim.max_val) if b is not None
              and judge(b, LAGOON, parameter_key=k) == NON_COMPLIANT]
    assert sorted(set(strict)) == sorted(set(COMPLIANCE_LIMITS) - {"ph"})


def test_the_verdict_string_is_underscored():
    """NON_COMPLIANT, matching ingestion/schema.py and the database.

    core/calculations.py::compliance_summary emits 'NON-COMPLIANT'; the §5
    step-2 note calls the substring bridge that papers over it fragile. Not
    copied.
    """
    assert judge(999, LAGOON, parameter_key="cod") == "NON_COMPLIANT"
    assert "-" not in judge(999, LAGOON, parameter_key="cod")


# ── Resolution never defaults ────────────────────────────────────────────────

LAGOON_ASSET = {"id": "a1", "organization_id": "org1", "asset_class": "sampled",
                "asset_type": "water_body", "scope": "lagoon"}


def test_resolves_the_built_in_set_for_a_scoped_asset():
    assert resolve_limits(LAGOON_ASSET, [LAGOON]) is LAGOON


@pytest.mark.parametrize("asset", [
    None,
    {},
    # Sampled, but nobody has said which specification set it lives under. 019:
    # NULL scope is a real answer meaning "cannot be judged yet".
    {"asset_class": "sampled", "asset_type": "water_body", "scope": None},
    {"asset_class": "sampled", "asset_type": "water_body"},
    # A scope the vocabulary does not contain is not a licence to guess.
    {"asset_class": "sampled", "asset_type": "water_body", "scope": "marine"},
    # Equipment has no specification set at all.
    {"asset_class": "equipment", "asset_type": "dosing", "scope": "lagoon"},
])
def test_unresolvable_assets_resolve_to_none(asset):
    assert resolve_limits(asset, [LAGOON]) is None


def test_a_facilities_asset_never_borrows_the_lagoon_set():
    """§7.4's central risk, stated as a test.

    900 CFU/L means one thing in a stored domestic tank and another in an open
    animal moat. The lagoon set is the only one seeded today; a facilities asset
    must resolve to None rather than be judged by it.
    """
    tank = {"organization_id": "org1", "asset_class": "sampled",
            "asset_type": "water_tank", "scope": "facilities"}
    assert resolve_limits(tank, [LAGOON]) is None


def test_none_resolution_never_yields_a_verdict():
    """The end-to-end guarantee: unresolved means unassessed, never a pass."""
    unclassified = {"asset_class": "sampled", "asset_type": "water_body"}
    limits = resolve_limits(unclassified, [LAGOON])
    assert limits is None
    for value in (0.0, 1.0, 49.0, 50.0, 10_000.0):
        assert judge(value, limits, parameter_key="cod") == NOT_ASSESSED


def test_an_empty_library_resolves_to_none():
    assert resolve_limits(LAGOON_ASSET, []) is None
    assert resolve_limits(LAGOON_ASSET) is None


def test_a_scope_unrestricted_set_is_never_selected_implicitly():
    """022: applies_to_scope NULL means the set must be selected explicitly."""
    loose = seeded_lagoon_set(key="client_special", applies_to_scope=None)
    assert resolve_limits(LAGOON_ASSET, [loose]) is None


def test_another_organisations_override_is_not_applied():
    theirs = seeded_lagoon_set(key="lagoon_dm_water", organization_id="org2")
    assert resolve_limits(LAGOON_ASSET, [theirs]) is None


def test_an_org_override_beats_the_built_in_it_narrows():
    mine = seeded_lagoon_set(organization_id="org1")
    assert resolve_limits(LAGOON_ASSET, [LAGOON, mine]) is mine


def test_two_equally_good_matches_resolve_to_none():
    """Ambiguity is the same confident-wrong-verdict failure wearing a face."""
    other = seeded_lagoon_set(key="lagoon_other")
    assert resolve_limits(LAGOON_ASSET, [LAGOON, other]) is None


def test_an_explicit_key_selects_one_set_but_cannot_cross_scope():
    other = seeded_lagoon_set(key="lagoon_other")
    asset = {**LAGOON_ASSET, "spec_set_key": "lagoon_other"}
    assert resolve_limits(asset, [LAGOON, other]) is other

    facilities_asset = {**LAGOON_ASSET, "scope": "facilities",
                        "spec_set_key": LAGOON_SET_KEY}
    assert resolve_limits(facilities_asset, [LAGOON]) is None


def test_a_parameter_the_set_does_not_judge_is_not_assessed():
    """A partial set leaves the rest unassessed — it never reaches for a
    neighbouring limit. See verify_complete() in db/seed_standards.py."""
    assert judge(9999, LAGOON, parameter_key="legionella_pneumophila") == NOT_ASSESSED


# ── Qualifier rules, one test per rule 022 permits ───────────────────────────

CEILING = SpecLimit("total_coliforms", "Total Coliforms", None, 1000, False,
                    False, "< 1000", "CFU/100mL", "bound")


def test_bound_rule_passes_a_non_detect_wholly_inside_the_limit():
    """022: '<4' against '< 100' is a genuine PASS — the whole possible range
    is compliant."""
    assert judge("<4", CEILING) == COMPLIANT
    assert judge({"parameter_key": "total_coliforms", "value_num": 4.0,
                  "qualifier": "<"}, LAGOON) == COMPLIANT


def test_bound_rule_refuses_to_fabricate_a_failure():
    """022: '<4' against '< 1' proves nothing and yields NOT_ASSESSED."""
    tight = SpecLimit("x", "X", None, 1, False, False, "< 1", "", "bound")
    assert judge("<4", tight) == NOT_ASSESSED


def test_bound_rule_fails_only_when_the_whole_range_fails():
    assert judge(">5000", CEILING) == NON_COMPLIANT
    # '<1000' against a ceiling of '< 1000' is a genuine PASS, and this is the
    # case the strictness data has to get right: the reported range is exactly
    # the permitted range, so every value it could be is compliant. Against an
    # INCLUSIVE ceiling it would also pass; against '< 999' it would not.
    assert judge("<1000", CEILING) == COMPLIANT
    assert judge("<1001", CEILING) == NOT_ASSESSED


def test_bound_rule_never_coerces_a_non_detect_to_zero():
    """Migration 016. A measured 0.0 would pass a floor; 'ND' must not.

    Dissolved oxygen is bounded below at 4.0. A measured 0.0 is an unambiguous
    breach; 'Not Detected' carries no magnitude at all, and the honest answer is
    that it cannot be judged against a floor.
    """
    do = seeded_limit("do")
    assert judge(0.0, do) == NON_COMPLIANT
    assert judge("ND", do) == NOT_ASSESSED
    assert judge("Not Detected", do) == NOT_ASSESSED


def test_bound_rule_passes_a_non_detect_against_a_ceiling():
    """Consistent with ingestion/gates.py, where ND satisfies a printed ceiling."""
    assert judge("ND", CEILING) == COMPLIANT
    assert judge("Absent/100mL", CEILING) == COMPLIANT


def test_bound_rule_uses_the_loq_when_the_certificate_states_one():
    tight = SpecLimit("x", "X", None, 1, False, False, "< 1", "", "bound")
    assert judge({"parameter_key": "x", "value_raw": "ND", "qualifier": "ND",
                  "loq": 0.5}, tight) == COMPLIANT
    assert judge({"parameter_key": "x", "value_raw": "ND", "qualifier": "ND",
                  "loq": 5.0}, tight) == NOT_ASSESSED


# A parameter where presence alone is the breach carries a ceiling of zero —
# that is what "Absent" means as a number, and 022 requires every limit to be
# bounded on at least one side.
DETECT = SpecLimit("legionella", "Legionella", None, 0, False, True,
                   "Absent", "CFU/L", "detect_fails")


def test_detect_fails_passes_a_non_detection_and_fails_any_detection():
    assert judge("ND", DETECT) == COMPLIANT
    assert judge("Absent/100mL", DETECT) == COMPLIANT
    # Below the limit of quantitation is not a detection. Under the 'bound' rule
    # '<1' against a ceiling of 0 would straddle and yield NOT_ASSESSED; this is
    # the divergence 'detect_fails' exists to express, and it matches
    # ingestion/gates.py:126 where '<' and 'ND' both satisfy a printed 'Absent'.
    assert judge("<1", DETECT) == COMPLIANT
    assert judge(1.0, DETECT) == NON_COMPLIANT
    assert judge(">10", DETECT) == NON_COMPLIANT
    # And a quantified zero still passes: it is a measurement of nothing found.
    assert judge(0.0, DETECT) == COMPLIANT


UNASSESSABLE = SpecLimit("x", "X", None, 100, False, False, "< 100", "",
                         "unassessable")


def test_unassessable_never_judges_a_qualified_value():
    for raw in ("<1", "ND", "Absent/100mL", ">500"):
        assert judge(raw, UNASSESSABLE) == NOT_ASSESSED, raw
    # A plain measurement is still judged normally — the rule is about
    # qualified values only.
    assert judge(50.0, UNASSESSABLE) == COMPLIANT
    assert judge(500.0, UNASSESSABLE) == NON_COMPLIANT


def test_an_unreadable_result_is_never_a_pass():
    assert judge("", CEILING) == NOT_ASSESSED
    assert judge("see attached report", CEILING) == NOT_ASSESSED
    assert judge({"parameter_key": "total_coliforms", "value_raw": "TNTC"},
                 LAGOON) == NOT_ASSESSED


def test_an_unrecognised_qualifier_is_not_ignored():
    """Whatever it meant, it modified the value — judging the bare number would
    assert something the laboratory did not."""
    assert judge({"parameter_key": "total_coliforms", "value_num": 5.0,
                  "qualifier": "~"}, LAGOON) == NOT_ASSESSED


# ── Between published bands ──────────────────────────────────────────────────

def test_a_value_between_published_bands_is_not_assessed():
    """Never snapped to the nearer band.

    A result that constrains the true value to a range spanning a published
    boundary sits between the bands, and no verdict follows from it. The
    temptation is to take the midpoint, or the reported magnitude, and judge that
    — both invent a number the certificate does not carry.
    """
    ecoli = seeded_limit("ecoli")           # < 200, exclusive
    assert judge("<500", ecoli) == NOT_ASSESSED     # spans 200
    assert judge(">100", ecoli) == NOT_ASSESSED     # spans 200 from below
    assert judge("<201", ecoli) == NOT_ASSESSED     # just past the bound
    assert judge("<200", ecoli) == COMPLIANT        # exactly the permitted range
    assert judge("<199", ecoli) == COMPLIANT        # wholly inside
    assert judge(">200", ecoli) == NON_COMPLIANT    # wholly outside


def test_ph_between_the_two_bands_of_a_two_sided_limit():
    ph = seeded_limit("ph")
    assert judge("<7", ph) == NOT_ASSESSED    # could be 3 or could be 6.5
    assert judge("<6", ph) == NON_COMPLIANT   # wholly below the floor
    assert judge(">9", ph) == NON_COMPLIANT
    assert judge(6.0, ph) == COMPLIANT        # inclusive both ends
    assert judge(9.0, ph) == COMPLIANT


# ── Unbounded sides ──────────────────────────────────────────────────────────

def test_an_unbounded_side_constrains_nothing():
    do = seeded_limit("do")                   # min 4.0 exclusive, no ceiling
    assert do.max_val is None
    assert judge(1_000_000.0, do) == COMPLIANT
    assert judge(4.0, do) == NON_COMPLIANT    # strict >, per calculations.py:28
    assert judge(4.000001, do) == COMPLIANT

    cod = seeded_limit("cod")                 # max 50 exclusive, no floor
    assert cod.min_val is None
    assert judge(-5.0, cod) == COMPLIANT      # nonsensical, but not a breach
    assert judge(50.0, cod) == NON_COMPLIANT


def test_a_limit_bounded_on_neither_side_is_rejected():
    """spec_limits_bounded_check, enforced here too: such a limit would pass
    every value put to it."""
    with pytest.raises(SpecError):
        SpecLimit("x", "X", None, None, False, False, "any", "", "bound")


def test_inclusivity_must_be_stated_and_is_never_read_from_the_display():
    """022: min_inclusive/max_inclusive are NOT NULL with no default, and
    `display` is output only."""
    with pytest.raises(SpecError):
        spec_limit_from_row({"parameter_key": "x", "parameter_label": "X",
                             "min_val": None, "max_val": 50,
                             "min_inclusive": None, "max_inclusive": False,
                             "display": "< 50"})

    # A display string that contradicts the booleans changes nothing: the data
    # wins. Here display says '≤ 50' while max_inclusive is False.
    lim = spec_limit_from_row({"parameter_key": "x", "parameter_label": "X",
                               "min_val": None, "max_val": 50,
                               "min_inclusive": False, "max_inclusive": False,
                               "display": "≤ 50"})
    assert judge(50.0, lim) == NON_COMPLIANT


def test_an_invalid_qualifier_rule_is_rejected():
    with pytest.raises(SpecError):
        SpecLimit("x", "X", None, 50, False, False, "< 50", "", "improvise")


# ── Row building ─────────────────────────────────────────────────────────────

def test_spec_set_from_rows_reads_postgrest_shapes():
    """NUMERIC may arrive as int, float or string."""
    spec = spec_set_from_rows(
        {"key": "facilities_potable_tank", "label": "Potable tank",
         "applies_to_scope": "facilities", "organization_id": None,
         "standard_id": "std-1"},
        [{"parameter_key": "Legionella_Pneumophila", "parameter_label": "Legionella",
          "unit": "CFU/L", "min_val": None, "max_val": "100.0000",
          "min_inclusive": False, "max_inclusive": False, "display": "< 100",
          "qualifier_rule": "bound"}],
    )
    assert spec.applies_to_scope == "facilities"
    lim = spec.limit_for("legionella_pneumophila")
    assert lim is not None and lim.max_val == 100.0
    assert judge(100.0, spec, parameter_key="legionella_pneumophila") == NON_COMPLIANT

    tank = {"organization_id": "org1", "asset_class": "sampled",
            "asset_type": "water_tank", "scope": "facilities"}
    assert resolve_limits(tank, [LAGOON, spec]) is spec
