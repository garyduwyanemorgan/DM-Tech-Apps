"""Gate 2 — extractor regression against hand-verified fixtures.

Before the Wimpey parser is trusted on *any* new report, it must still reproduce
known-correct output for every form type. This gates the extractor, not the
document, in the same way a CI suite gates a code change.

Ground truth lives in fixtures/wimpey/expected_values.json and was transcribed by
hand from the printed PDFs. Do not regenerate it from parser output — that would
make the test tautological and would have hidden the sign-off row that this suite
originally caught being parsed as a 24th chemistry parameter.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from ingestion import gates
from ingestion.schema import ResultStatus
from ingestion.wimpey import WimpeyParseError, detect_form_type, is_wimpey_report, parse

FIXTURES = Path(__file__).parent / "fixtures" / "wimpey"
EXPECTED = json.loads((FIXTURES / "expected_values.json").read_text(encoding="utf-8"))
REPORTS = [k for k in EXPECTED if not k.startswith("_")]

# Header fields compared verbatim for every fixture.
_TEXT_FIELDS = [
    "laboratory", "report_no", "form_type", "report_type",
    "sampling_point", "sample_location", "sample_identification",
    "source_of_sample", "sample_description", "sampling_time",
    "sampled_by", "sampling_method", "sampling_apparatus", "sample_volume",
    "analyst", "reviewed_by",
]
_DATE_FIELDS = ["sampled_at", "received_at", "reported_at", "analysis_start", "analysis_end"]


def _load(name: str):
    return parse((FIXTURES / name).read_bytes(), name)


@pytest.mark.parametrize("name", REPORTS)
def test_header_fields_match_ground_truth(name):
    sample = _load(name)
    expected = EXPECTED[name]
    for field in _TEXT_FIELDS:
        assert getattr(sample, field) == expected[field], f"{name}: {field}"


@pytest.mark.parametrize("name", REPORTS)
def test_dates_match_ground_truth(name):
    sample = _load(name)
    for field in _DATE_FIELDS:
        assert getattr(sample, field) == date.fromisoformat(EXPECTED[name][field]), \
            f"{name}: {field}"


@pytest.mark.parametrize("name", REPORTS)
def test_temperature_matches(name):
    assert _load(name).temperature_c == pytest.approx(EXPECTED[name]["temperature_c"])


@pytest.mark.parametrize("name", REPORTS)
def test_result_count_matches(name):
    """The sign-off block is ruled into the results table but is not a parameter."""
    assert len(_load(name).results) == EXPECTED[name]["results_count"]


@pytest.mark.parametrize("name", REPORTS)
def test_every_result_row_matches(name):
    sample = _load(name)
    for got, want in zip(sample.results, EXPECTED[name]["results"]):
        for field in ("parameter", "test_method", "unit", "value_raw", "qualifier"):
            assert getattr(got, field) == want[field], f"{name}: {want['parameter']}.{field}"
        if want["value_num"] is None:
            assert got.value_num is None, f"{name}: {want['parameter']}.value_num"
        else:
            assert got.value_num == pytest.approx(want["value_num"])
        if "loq" in want:
            if want["loq"] is None:
                assert got.loq is None, f"{name}: {want['parameter']}.loq"
            else:
                assert got.loq == pytest.approx(want["loq"])
        if "specification" in want:
            assert got.specification == want["specification"]
        if "mou" in want:
            assert got.mou == want["mou"]


@pytest.mark.parametrize("name", REPORTS)
def test_verbatim_values_never_coerced(name):
    """'<1' and 'Not Detected' must survive intact — they are regulatory statements."""
    for result in _load(name).results:
        assert result.value_raw.strip(), f"{name}: {result.parameter} lost its printed value"
        if result.qualifier == "ND":
            assert result.value_num is None, \
                f"{name}: {result.parameter} invented a magnitude for a non-detect"


@pytest.mark.parametrize("name", REPORTS)
def test_provenance_is_bound(name):
    """Gate 5 — nothing proceeds without knowing where it came from."""
    sample = _load(name)
    assert len(sample.source_sha256) == 64
    assert sample.extraction_method == "wimpey-pdf-text"
    assert sample.extraction_confidence == 1.0
    assert sample.raw_extraction, "gate 7 audit trail is empty"
    gates.bind_provenance(sample)


@pytest.mark.parametrize("name", REPORTS)
def test_gates_find_no_anomalies_in_known_good_reports(name):
    """All three fixtures are clean reports; any anomaly means a parser regression."""
    sample = gates.apply(_load(name))
    assert sample.anomalies == [], f"{name}: {sample.anomalies}"


@pytest.mark.parametrize("name", REPORTS)
def test_nothing_auto_approves(name):
    """Gate 6 — parsing never commits data, however confident the extractor is."""
    assert gates.apply(_load(name)).reviewer_status.value == "pending"


def test_printed_specification_verdicts():
    """Statuses are read off the limit printed on the report, not a rules engine."""
    sample = gates.apply(_load("WD-R-260421-0222_microbiology.pdf"))
    for got, want in zip(sample.results, EXPECTED["WD-R-260421-0222_microbiology.pdf"]["results"]):
        assert got.status.value == want["status"], want["parameter"]
    assert gates.failing_results(sample) == []


def test_chemistry_has_no_specification_so_is_not_assessed():
    """The chemistry form prints LOQ but no limits — inventing a verdict would be wrong."""
    sample = gates.apply(_load("WD-R-260616-0203_chemistry.pdf"))
    assert all(r.status is ResultStatus.NOT_ASSESSED for r in sample.results)


def test_detects_and_rejects_non_wimpey_input():
    assert detect_form_type("Form No: WRF2-W-001 Issue No.:01") == "WRF2-W-001"
    assert detect_form_type("some other laboratory report") is None
    assert not is_wimpey_report(b"%PDF-1.4 not really a pdf")
    with pytest.raises(WimpeyParseError):
        parse((FIXTURES / "expected_values.json").read_bytes(), "not-a-pdf.json")


@pytest.mark.parametrize("name", REPORTS)
def test_is_wimpey_report_recognises_every_fixture(name):
    assert is_wimpey_report((FIXTURES / name).read_bytes())
