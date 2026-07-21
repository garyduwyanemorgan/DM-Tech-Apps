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
from ingestion.schema import ComplianceStatus, LabResult, LabSample, ResultStatus
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

# The governing standard cited in the certificate footer, plus the legionella
# method disclosure. Compared verbatim: a citation quoted back to a regulator has
# to match the certificate it came from.
_STANDARD_FIELDS = [
    "standard_code", "standard_title", "standard_year", "standard_authority",
    "standard_citation", "test_procedure", "medium_used",
    "detection_limit", "filtered_volume",
]


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
def test_gates_find_no_parser_anomalies_in_known_good_reports(name):
    """All three fixtures parse cleanly; any [parser] anomaly is a regression.

    [source] findings are a different thing: they are true statements about the
    document, not faults in our reading of it. These certificates legitimately
    carry one — they cite a superseded edition of GU44 — so the assertion is
    scoped to parser faults rather than demanding an empty list.
    """
    sample = gates.apply(_load(name))
    parser_faults = [a for a in sample.anomalies if a.startswith("[parser]")]
    assert parser_faults == [], f"{name}: {parser_faults}"


@pytest.mark.parametrize("name", ["WD-R-260421-0222_microbiology.pdf",
                                  "WD-R-260421-0235_legionella.pdf"])
def test_superseded_gu44_citation_is_flagged(name):
    """Both certificates cite DM-HSD-GU44-LCWS2 edition 2024 despite being
    sampled in 2026, after V6 was issued on 19 August 2025. The limits are
    unchanged, so the verdicts stand — but a regulator can reasonably ask why a
    2026 certificate names a superseded document, and the client should hear it
    from us first."""
    sample = gates.apply(_load(name))
    stale = [a for a in sample.anomalies if "superseding" in a]
    assert len(stale) == 1, sample.anomalies
    assert "DM-HSD-GU44-LCWS2" in stale[0] and "2025-08-19" in stale[0]


def test_a_certificate_citing_no_standard_is_not_flagged():
    """The chemistry form cites nothing, so there is no edition to be stale."""
    sample = gates.apply(_load("WD-R-260616-0203_chemistry.pdf"))
    assert not any("superseding" in a for a in sample.anomalies)


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


@pytest.mark.parametrize("name", REPORTS)
def test_governing_standard_matches_ground_truth(name):
    """The footer citation is the only record of which limits were applied."""
    sample = _load(name)
    expected = EXPECTED[name]
    for field in _STANDARD_FIELDS:
        assert getattr(sample, field) == expected[field], f"{name}: {field}"
    assert sample.additional_standards == expected["additional_standards"], name


def test_chemistry_invents_no_standard():
    """The chemistry form cites nothing; a plausible-looking standard here would
    be this system asserting a limit the laboratory never applied."""
    sample = _load("WD-R-260616-0203_chemistry.pdf")
    for field in _STANDARD_FIELDS:
        assert getattr(sample, field) == "", field
    assert sample.additional_standards == []


def test_printed_case_of_the_standard_title_is_preserved():
    """The two forms disagree — 'water System' vs 'Water System'. Both are quoted
    as printed; tidying either would misquote a certificate."""
    micro = _load("WD-R-260421-0222_microbiology.pdf")
    legio = _load("WD-R-260421-0235_legionella.pdf")
    assert micro.standard_title.endswith("in water System")
    assert legio.standard_title.endswith("in Water System")
    assert micro.standard_code == legio.standard_code == "DM-HSD-GU44-LCWS2"


@pytest.mark.parametrize("name", REPORTS)
def test_overall_status_matches_ground_truth(name):
    sample = gates.apply(_load(name))
    assert sample.overall_status.value == EXPECTED[name]["overall_status"], name


def test_unassessed_report_is_never_compliant():
    """The safety-critical rule: absence of a verdict must not read as a pass."""
    chemistry = gates.apply(_load("WD-R-260616-0203_chemistry.pdf"))
    assert any(r.status is ResultStatus.NOT_ASSESSED for r in chemistry.results)
    assert chemistry.overall_status is ComplianceStatus.INCOMPLETE

    passing = LabResult(parameter="Total Coliforms", value_raw="<1",
                        status=ResultStatus.PASS)
    unknown = LabResult(parameter="Turbidity", value_raw="8.9",
                        status=ResultStatus.NOT_ASSESSED)
    failing = LabResult(parameter="E. coli", value_raw="12",
                        status=ResultStatus.FAIL)

    assert gates.roll_up_status([passing]) is ComplianceStatus.COMPLIANT
    # One unassessed parameter downgrades a certificate of otherwise clean rows.
    assert gates.roll_up_status([passing, unknown]) is ComplianceStatus.INCOMPLETE
    # A failure outranks an unknown: the worst known verdict wins.
    assert gates.roll_up_status([passing, unknown, failing]) is \
        ComplianceStatus.NON_COMPLIANT
    # An empty results table is the trap `all(...)` would fall into.
    assert gates.roll_up_status([]) is ComplianceStatus.INCOMPLETE


def test_unparsed_sample_defaults_to_incomplete():
    """A LabSample that never reached the gates must not claim compliance."""
    sample = LabSample(laboratory="Wimpey Laboratories", report_no="X-1",
                       form_type="WRF2-W-001", report_type="microbiology")
    assert sample.overall_status is ComplianceStatus.INCOMPLETE


@pytest.mark.parametrize("name", REPORTS)
def test_every_result_explains_its_verdict(name):
    """A verdict a reviewer cannot act on is not much better than no verdict."""
    for result in gates.apply(_load(name)).results:
        assert result.status_reason.strip(), f"{name}: {result.parameter}"


def test_not_assessed_reasons_distinguish_cause_and_never_read_as_a_pass():
    """Missing limit vs unreadable limit need different follow-up, and neither is
    a pass — the wording has to say so out loud."""
    no_spec = LabResult(parameter="Turbidity", value_raw="8.9", value_num=8.9)
    status, reason = gates.evaluate_printed_spec(no_spec)
    assert status is ResultStatus.NOT_ASSESSED
    assert "No specification was printed" in reason
    assert "not a pass" in reason

    odd_spec = LabResult(parameter="Colour", value_raw="8.9", value_num=8.9,
                         specification="As per DM guideline")
    status, reason = gates.evaluate_printed_spec(odd_spec)
    assert status is ResultStatus.NOT_ASSESSED
    assert "not in a form this system can interpret" in reason
    assert "not a pass" in reason

    # "<5000" against a limit of 1000 bounds the result above the limit: it
    # neither demonstrates compliance nor proves an exceedance.
    loose = LabResult(parameter="Enumeration of legionella", value_raw="<5000",
                      value_num=5000.0, qualifier="<", specification="<1000")
    status, reason = gates.evaluate_printed_spec(loose)
    assert status is ResultStatus.NOT_ASSESSED
    assert "not a pass" in reason


def test_detects_and_rejects_non_wimpey_input():
    assert detect_form_type("Form No: WRF2-W-001 Issue No.:01") == "WRF2-W-001"
    assert detect_form_type("some other laboratory report") is None
    assert not is_wimpey_report(b"%PDF-1.4 not really a pdf")
    with pytest.raises(WimpeyParseError):
        parse((FIXTURES / "expected_values.json").read_bytes(), "not-a-pdf.json")


@pytest.mark.parametrize("name", REPORTS)
def test_is_wimpey_report_recognises_every_fixture(name):
    assert is_wimpey_report((FIXTURES / name).read_bytes())
