"""The strictness glyph on a printed specification is part of the limit.

A laboratory that prints "<1000" has stated that 1000 itself is out of
specification; "≤1000" and a bare "1000" admit it. `evaluate_printed_spec` used
to match the glyph and discard it, so all three read as the same inclusive
ceiling and a result of exactly 1000 against a printed "<1000" passed. That is a
verdict we would have had to defend against the accredited laboratory whose
certificate we were quoting.

These tests pin the operator semantics *and* the fail-closed behaviour around
them: nothing unreadable, absent or unqualified may become a pass.
"""
from __future__ import annotations

import pytest

from ingestion import gates
from ingestion.schema import LabResult, ResultStatus


def _result(**kw) -> LabResult:
    kw.setdefault("parameter", "Total Coliforms")
    kw.setdefault("unit", "CFU/100ml")
    return LabResult(**kw)


def _judge(value: float, spec: str, qualifier=None, raw=None):
    r = _result(value_raw=raw if raw is not None else str(value),
                value_num=value, qualifier=qualifier, specification=spec)
    return gates.evaluate_printed_spec(r)


# ── exactly at the limit: the whole point of the fix ──

def test_exactly_at_an_exclusive_limit_fails():
    status, reason = _judge(1000.0, "<1000")
    assert status is ResultStatus.FAIL
    assert "exclusively" in reason


def test_exactly_at_an_inclusive_limit_passes():
    """'≤' means at-or-below, so the bound itself is inside the specification."""
    status, reason = _judge(1000.0, "≤1000")
    assert status is ResultStatus.PASS
    assert "within the printed limit" in reason


def test_exactly_at_a_bare_limit_passes():
    """A printed maximum with no operator keeps its conventional inclusive
    reading — this fix narrows '<' only, it does not re-judge plain numbers."""
    assert _judge(1000.0, "1000")[0] is ResultStatus.PASS
    assert _judge(500.0, "500*")[0] is ResultStatus.PASS   # trailing footnote marker


# ── either side of the limit: unchanged for every operator ──

@pytest.mark.parametrize("spec", ["<1000", "≤1000", "1000"])
def test_below_the_limit_passes_whatever_the_operator(spec):
    assert _judge(999.0, spec)[0] is ResultStatus.PASS


@pytest.mark.parametrize("spec", ["<1000", "≤1000", "1000"])
def test_above_the_limit_fails_whatever_the_operator(spec):
    status, reason = _judge(1001.0, spec)
    assert status is ResultStatus.FAIL
    assert "exceeds the printed limit" in reason


def test_decimal_limits_carry_the_operator_too():
    assert _judge(0.5, "<0.5")[0] is ResultStatus.FAIL
    assert _judge(0.5, "0.5")[0] is ResultStatus.PASS
    assert _judge(0.49, "<0.5")[0] is ResultStatus.PASS


# ── a result that is itself a bound ──

def test_a_bounded_result_at_the_limit_passes_even_against_an_exclusive_spec():
    """'<1000' reported against a printed '<1000' says the true value lies below
    1000, which satisfies an exclusive limit as well as an inclusive one."""
    status, _ = _judge(1000.0, "<1000", qualifier="<", raw="<1000")
    assert status is ResultStatus.PASS


def test_a_bounded_result_above_the_limit_is_not_assessed():
    status, reason = _judge(5000.0, "<1000", qualifier="<", raw="<5000")
    assert status is ResultStatus.NOT_ASSESSED
    assert "not a pass" in reason


def test_not_detected_passes_any_numeric_ceiling():
    for spec in ("<1000", "≤1000", "1000"):
        status, _ = _judge(None, spec, qualifier="ND", raw="Not Detected")
        assert status is ResultStatus.PASS


# ── the detect-fails path must be untouched ──

@pytest.mark.parametrize("spec", ["Zero", "Absent", "nil", "Not Detected", "not detected"])
def test_zero_specs_pass_only_on_a_non_detection(spec):
    assert _judge(None, spec, qualifier="ND", raw="Not Detected")[0] is ResultStatus.PASS
    assert _judge(1.0, spec, qualifier="<", raw="<1")[0] is ResultStatus.PASS


@pytest.mark.parametrize("spec", ["Zero", "Absent", "nil", "Not Detected"])
def test_zero_specs_fail_on_any_detection(spec):
    status, reason = _judge(1.0, spec, raw="1")
    assert status is ResultStatus.FAIL
    assert "none are permitted" in reason


def test_zero_spec_with_an_unreadable_result_is_not_assessed():
    status, reason = _judge(None, "Zero", raw="see comment")
    assert status is ResultStatus.NOT_ASSESSED
    assert "not a pass" in reason


# ── fail-closed: nothing unreadable may become a pass ──

@pytest.mark.parametrize("spec", ["", "   ", "-"])
def test_absent_specification_is_not_assessed(spec):
    status, reason = _judge(1000.0, spec)
    assert status is ResultStatus.NOT_ASSESSED
    assert "not a pass" in reason


@pytest.mark.parametrize("spec", [
    "As per DM guideline", "<1000 CFU", "1000-2000", ">1000", "≤ 1,000",
    "less than 1000", "<", "N/A",
])
def test_unreadable_specification_is_not_assessed(spec):
    status, reason = _judge(1000.0, spec)
    assert status is ResultStatus.NOT_ASSESSED
    assert "not in a form this system can interpret" in reason
    assert "not a pass" in reason


def test_a_numeric_limit_with_no_number_to_compare_is_not_assessed():
    status, reason = _judge(None, "<1000", raw="see comment")
    assert status is ResultStatus.NOT_ASSESSED
    assert "not a pass" in reason


def test_whitespace_between_operator_and_number_is_tolerated():
    assert _judge(1000.0, "< 1000")[0] is ResultStatus.FAIL
    assert _judge(1000.0, "≤ 1000")[0] is ResultStatus.PASS
