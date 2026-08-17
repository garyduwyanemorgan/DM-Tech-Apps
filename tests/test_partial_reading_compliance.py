"""A partially-measured reading must not crash, and must not read as a pass.

`insert_reading` accepts a partial `fields` dict, so a reading can legitimately
carry only some parameters. Before this, `check_compliance` compared None
against a numeric limit and raised:

    TypeError: '<' not supported between instances of 'NoneType' and 'int'

which took `GET /status/{site}` down with a 500 (found while verifying the RLS
work — a seeded reading with NULL metrics reproduced it exactly).

Not crashing is the easy half. The half that matters is that a reading with one
measured parameter out of ten must not report "100% COMPLIANT". That is a
compliance claim no laboratory made, on regulated data submitted to a
regulator. The rule mirrors the one already written down for certificate
verdicts in db/queries.py's `_compliance_kpi`: INCOMPLETE is its own bucket,
and folding it into `compliant` is never allowed.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.calculations import (  # noqa: E402
    check_all_compliance,
    check_compliance,
    compliance_summary,
)
from core.models import WaterReading  # noqa: E402


def _reading(**overrides) -> WaterReading:
    """A fully compliant reading, unless a field is overridden with None."""
    base = dict(
        timestamp=datetime(2026, 3, 15),
        ph=7.9, do=6.4, tss=12.0, turbidity=4.2, cod=38.0,
        ammonia=0.4, phosphate=0.8, oil_grease=1.1, ecoli=30.0,
        total_coliforms=120.0, chla=9.0, phycocyanin=2.0,
        salinity=44.5, water_temp=29.3,
    )
    base.update(overrides)
    return WaterReading(**base)


# ── The crash ─────────────────────────────────────────────────────────────────

def test_a_single_missing_parameter_does_not_raise():
    """The original bug, at its smallest."""
    result = check_compliance("cod", None)
    assert result.measured is False


def test_the_reading_that_produced_the_500_is_handled():
    """Exactly the shape seeded during the RLS verification: metrics NULL."""
    reading = _reading(cod=None, ammonia=None, phosphate=None,
                       turbidity=None, oil_grease=None, ecoli=None)
    results = check_all_compliance(reading)          # used to raise TypeError
    summary = compliance_summary(results)
    assert summary["missing_count"] == 6
    assert summary["measured_count"] == len(results) - 6


# ── The dangerous half: an incomplete reading is not a pass ───────────────────

def test_one_measured_parameter_is_not_a_hundred_percent_pass():
    """The whole point. Averaging over present values alone would say COMPLIANT."""
    reading = _reading(do=None, tss=None, turbidity=None, cod=None,
                       ammonia=None, phosphate=None, oil_grease=None,
                       ecoli=None, total_coliforms=None)
    summary = compliance_summary(check_all_compliance(reading))
    assert summary["measured_count"] == 1
    assert summary["overall_status"] == "INCOMPLETE", (
        "a reading with one measured parameter must never report COMPLIANT"
    )


def test_a_missing_parameter_is_not_counted_as_a_failure_either():
    """Unmeasured is not a breach: nobody claimed one."""
    reading = _reading(cod=None)
    summary = compliance_summary(check_all_compliance(reading))
    assert summary["failing_count"] == 0
    assert "COD" not in " ".join(summary["failing_params"]).upper() or \
           summary["failing_count"] == 0
    assert summary["missing_count"] == 1


def test_nothing_measured_at_all_is_incomplete_not_compliant():
    reading = _reading(ph=None, do=None, tss=None, turbidity=None, cod=None,
                       ammonia=None, phosphate=None, oil_grease=None,
                       ecoli=None, total_coliforms=None)
    summary = compliance_summary(check_all_compliance(reading))
    assert summary["measured_count"] == 0
    assert summary["overall_status"] == "INCOMPLETE"
    assert summary["compliance_pct"] == 0


def test_missing_parameters_are_named_so_the_gap_is_visible():
    """An invisible gap is the failure mode this codebase keeps hitting."""
    summary = compliance_summary(check_all_compliance(_reading(cod=None, ecoli=None)))
    assert len(summary["missing_params"]) == 2
    assert all(isinstance(n, str) and n for n in summary["missing_params"])


# ── Unchanged behaviour for complete readings ─────────────────────────────────

def test_a_complete_compliant_reading_still_reports_compliant():
    """The regression guard: the fix must not make good readings INCOMPLETE."""
    summary = compliance_summary(check_all_compliance(_reading()))
    assert summary["missing_count"] == 0
    assert summary["overall_status"] == "COMPLIANT"
    assert summary["compliance_pct"] == 100.0


def test_a_complete_breaching_reading_still_reports_non_compliant():
    summary = compliance_summary(check_all_compliance(_reading(ph=2.0)))
    assert summary["missing_count"] == 0
    assert summary["overall_status"] == "NON-COMPLIANT"
    assert summary["failing_count"] >= 1


def test_min_margin_ignores_unmeasured_parameters():
    """An unmeasured parameter carries margin 0.0, which would read as a
    hair's-breadth pass if it were included. min_margin must describe only
    what was actually measured.

    Note this is NOT "the value is unchanged": dropping a measured parameter
    legitimately changes the minimum when that parameter held it. The property
    is that the placeholder zero never becomes the answer.
    """
    partial = compliance_summary(check_all_compliance(_reading(cod=None, ecoli=None)))
    assert partial["missing_count"] == 2
    assert partial["min_margin"] > 0, "a placeholder 0.0 leaked into min_margin"

    # And with nothing measured there is no margin to report, not a zero one.
    empty = compliance_summary([])
    assert empty["min_margin"] == 0


# ── The endpoint that crashed ─────────────────────────────────────────────────

def test_assess_survives_a_partial_reading():
    """`_assess` is what GET /status/{site} calls at api_server.py:1723."""
    api_server = pytest.importorskip("api_server")
    out = api_server._assess(_reading(cod=None, ammonia=None))
    assert out["compliance"]["overall_status"] == "INCOMPLETE"
    assert out["compliance"]["missing_count"] == 2
    unmeasured = [p for p in out["compliance"]["per_parameter"] if not p["measured"]]
    assert len(unmeasured) == 2
    assert all(p["value"] is None for p in unmeasured)


# ── The alert engine: the second crash site ───────────────────────────────────
#
# Fixing check_compliance alone was NOT enough. `_assess` also calls
# evaluate_alert_level, which compared chla/do/phycocyanin/water_temp against
# numbers with no None guard. The unit tests above all passed while the endpoint
# still 500'd, because the helper here sets chla — only the end-to-end
# reproduction against a real NULL-metric row exposed it. Hence these.

def test_alert_engine_survives_missing_bloom_inputs():
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading(chla=None, phycocyanin=None))
    assert state is not None


def test_bloom_probability_is_none_not_zero_when_unmeasured():
    """0.0 asserts there is no bloom risk. None admits nobody looked."""
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading(chla=None))
    assert state.bloom_probability is None


def test_unmeasured_drivers_are_named_so_green_is_not_mistaken_for_healthy():
    """There is no UNKNOWN alert level, so the gap has to show up in drivers."""
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading(chla=None, phycocyanin=None))
    drivers = " ".join(state.top_drivers)
    assert "not measured" in drivers.lower()
    assert "Chl-a" in drivers and "Phycocyanin" in drivers


def test_a_real_trigger_still_leads_the_driver_list():
    """A genuine escalation must not be buried behind the not-measured note."""
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading(chla=None, water_temp=31.0))
    assert "not measured" not in state.top_drivers[0].lower()
    assert state.escalation_reason and "31" in state.escalation_reason


def test_species_is_unknown_rather_than_no_bloom_when_unmeasured():
    """"No bloom" would be a finding; "unknown" is the truth."""
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading(chla=None))
    assert "unknown" in state.dominant_species.lower()


def test_a_complete_reading_still_gets_a_real_bloom_probability():
    from core.alert_engine import evaluate_alert_level
    state = evaluate_alert_level(_reading())
    assert isinstance(state.bloom_probability, float)
    assert "not measured" not in " ".join(state.top_drivers).lower()
