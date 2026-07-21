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

    results: list[LabResult] = Field(default_factory=list)

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
