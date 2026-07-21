"""Typed schema for extracted lab data — Gate 1 of the assurance gateway.

Strict and fail-closed: a malformed report raises rather than silently yielding a
half-populated record with defaults standing in for missing values. A rejected
report is visible; a defaulted one is not, and this data ends up in front of a
regulator.

`value_raw` is preserved exactly as printed. "<1" and "Not Detected" are
regulatorily meaningful statements about the detection limit — coercing either to
0.0 would assert something the laboratory did not.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ResultStatus(str, Enum):
    """Compliance verdict for a single parameter."""
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"      # no specification printed on the report


class ComplianceStatus(str, Enum):
    """Certificate-level verdict rolled up from every parameter row.

    INCOMPLETE is deliberately a third state rather than a flavour of pass. The
    client asks one question of this app — "did we meet the guidelines?" — and the
    only honest answers are yes, no, and "this certificate does not say". Folding
    the third into the first is the failure mode that puts an unassessed report in
    front of Dubai Municipality wearing a green tick.
    """
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    INCOMPLETE = "INCOMPLETE"


class ReviewerStatus(str, Enum):
    """Gate 6 — where a record sits in the human-review queue."""
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class LabResult(BaseModel):
    """One parameter row from the report's results table."""

    parameter: str
    test_method: str = ""
    unit: str = ""

    value_raw: str                      # verbatim: "<1", "Not Detected", "30.4"
    value_num: Optional[float] = None   # parsed magnitude; None when non-numeric
    qualifier: Optional[str] = None     # "<", ">", "ND" — None for a plain number

    loq: Optional[float] = None         # limit of quantitation / detection
    mou: str = ""                       # measurement uncertainty, e.g. "6.46%"
    specification: str = ""             # e.g. "Zero", "<1000", "500*"

    status: ResultStatus = ResultStatus.NOT_ASSESSED
    # Why that status, in one sentence aimed at a reviewer who is not a chemist.
    # A bare NOT_ASSESSED tells nobody whether to chase the laboratory for a
    # missing limit or to fix our parser, and the two need different phone calls.
    status_reason: str = ""

    @field_validator("parameter")
    @classmethod
    def _parameter_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("parameter name is blank — table parsed misaligned")
        return v.strip()


class LabSample(BaseModel):
    """One laboratory report: its provenance header plus every parameter row."""

    # ── identity ──
    laboratory: str
    report_no: str
    form_type: str                      # "WRF2-W-001" — the lab's form revision
    report_type: str                    # chemistry | microbiology | legionella

    # ── what was sampled ──
    sampling_point: str = ""
    sample_location: str = ""
    sample_identification: str = ""
    source_of_sample: str = ""
    sample_description: str = ""

    # ── when ──
    sampled_at: Optional[date] = None
    received_at: Optional[date] = None
    reported_at: Optional[date] = None
    analysis_start: Optional[date] = None
    analysis_end: Optional[date] = None
    sampling_time: str = ""

    # ── how ──
    sampled_by: str = ""
    sampling_method: str = ""
    sampling_apparatus: str = ""
    sample_volume: str = ""
    temperature_c: Optional[float] = None
    analyst: str = ""
    reviewed_by: str = ""
    remarks: str = ""

    # ── against what (the governing standard cited in the certificate footer) ──
    # A result is only meaningful next to the limit it was judged against. The
    # certificates name that standard in a free-text footnote, so it is captured
    # verbatim in `standard_citation` and merely *indexed* by the parsed parts —
    # if the two ever disagree, the verbatim block is the one to trust.
    standard_code: str = ""             # "DM-HSD-GU44-LCWS2"
    standard_title: str = ""            # printed case preserved, incl. "water System"
    standard_year: str = ""             # str, not int: it is a citation, not arithmetic
    standard_authority: str = ""        # the issuing department, as printed
    standard_citation: str = ""         # the whole footer block, whitespace-normalised
    additional_standards: list[str] = Field(default_factory=list)   # e.g. ["GSO 149/2021"]

    # ── legionella method disclosure ──
    # Printed only on the legionella form. The detection limit is what makes
    # "Not Detected" a quantitative statement rather than a shrug.
    test_procedure: str = ""            # "7"
    medium_used: str = ""               # "BCYE+Cys+GVPC"
    detection_limit: str = ""           # "4 cfu/l" — verbatim, unit inseparable
    filtered_volume: str = ""           # "250 ml"

    results: list[LabResult] = Field(default_factory=list)

    # Rolled up by gates.apply(); INCOMPLETE until something computes it, so a
    # sample that never passed through the gates cannot read as compliant.
    overall_status: ComplianceStatus = ComplianceStatus.INCOMPLETE

    # ── provenance (Gate 5) + audit trail (Gate 7) ──
    source_filename: str = ""
    source_sha256: str = ""
    extraction_method: str = ""         # "wimpey-pdf-text" | "claude-vision"
    extraction_confidence: float = 0.0
    reviewer_status: ReviewerStatus = ReviewerStatus.PENDING
    raw_extraction: dict = Field(default_factory=dict)
    anomalies: list[str] = Field(default_factory=list)

    @field_validator("report_no")
    @classmethod
    def _report_no_present(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("report_no is required — cannot bind provenance without it")
        return v.strip()

    @field_validator("temperature_c")
    @classmethod
    def _temperature_plausible(cls, v: Optional[float]) -> Optional[float]:
        # Field sampling in the UAE; anything outside this is a parse error, not a reading.
        if v is not None and not (0.0 <= v <= 60.0):
            raise ValueError(f"temperature {v}degC outside plausible range 0-60")
        return v
