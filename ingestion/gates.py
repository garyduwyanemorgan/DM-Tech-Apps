"""Assurance gates — what turns an extraction into defensible data.

A parser reading a value off a PDF is a hypothesis. These gates are what make it
admissible. Implements gates 3, 5 and 6 of the lab-data assurance gateway; gate 1
is the schema in schema.py, gate 2 is tests/test_wimpey_parser.py, and gate 7 is
the untouched `raw_extraction` blob carried on every LabSample.

Nothing here silently drops or repairs a record. A failure is *classified* —
parser bug versus genuine source-document anomaly — and that classification is
itself part of the audit trail, because the two demand opposite responses: fix
our code, or go back to the laboratory.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ingestion.schema import LabResult, LabSample, ResultStatus, ReviewerStatus

logger = logging.getLogger(__name__)

# Below this, a record always queues for human review regardless of anomalies.
CONFIDENCE_THRESHOLD = 0.95


class GateFailure(Exception):
    """A record cannot proceed — provenance is unbindable."""


def check_consistency(sample: LabSample) -> list[str]:
    """Gate 3 — domain arithmetic and internal coherence.

    Returns a list of human-readable anomalies, each tagged [parser] or [source].
    An empty list means the report is internally coherent. Findings are returned,
    never raised: a genuine laboratory anomaly is a finding about the *document*
    and must survive into the record, not abort the ingest.
    """
    anomalies: list[str] = []

    # ── chronology ──
    d = {
        "sampled": sample.sampled_at,
        "received": sample.received_at,
        "analysis start": sample.analysis_start,
        "analysis end": sample.analysis_end,
        "reported": sample.reported_at,
    }
    order = ["sampled", "received", "analysis start", "analysis end", "reported"]
    known = [(n, d[n]) for n in order if d[n] is not None]
    for (n1, d1), (n2, d2) in zip(known, known[1:]):
        if d1 > d2:
            anomalies.append(f"[source] {n2} date {d2} precedes {n1} date {d1}")

    missing = [n for n, v in d.items() if v is None]
    if missing:
        anomalies.append(f"[parser] date(s) not extracted: {', '.join(missing)}")

    # ── results table ──
    if not sample.results:
        anomalies.append("[parser] no parameter rows extracted from the results table")

    for r in sample.results:
        if not r.unit and r.value_num is not None:
            anomalies.append(f"[parser] '{r.parameter}' has a numeric result but no unit")
        if not r.test_method:
            anomalies.append(f"[parser] '{r.parameter}' has no test method")
        if r.qualifier == "ND" and r.value_num is not None:
            anomalies.append(
                f"[parser] '{r.parameter}' is Not Detected but carries a magnitude")
        if r.qualifier in ("<", ">") and r.value_num is None:
            anomalies.append(
                f"[parser] '{r.parameter}' is qualified '{r.qualifier}' with no magnitude")
        if r.loq is not None and r.value_num is not None and r.qualifier is None:
            if r.value_num < r.loq:
                anomalies.append(
                    f"[source] '{r.parameter}' reports {r.value_num} below its LOQ {r.loq} "
                    "without a '<' qualifier")

    # ── identity ──
    if not sample.sampling_point:
        anomalies.append("[parser] no sampling point — the record cannot be tied to an asset")

    return anomalies


def evaluate_printed_spec(result: LabResult) -> ResultStatus:
    """Compare a result against the specification *printed on the same report*.

    Deliberately not a compliance engine: it applies no Dubai Municipality rules
    and no SOP knowledge, it only reads the limit the laboratory itself stated.
    Anything it cannot interpret with certainty is NOT_ASSESSED — an unreadable
    limit must never silently read as a pass.
    """
    spec = (result.specification or "").strip()
    if not spec or spec == "-":
        return ResultStatus.NOT_ASSESSED

    # "Zero" / "Absent" — any detection is a failure.
    if re.match(r"(?i)^(zero|absent|nil|not\s*detected)$", spec):
        if result.qualifier in ("ND", "<"):
            return ResultStatus.PASS
        if result.value_num is not None and result.value_num > 0:
            return ResultStatus.FAIL
        return ResultStatus.NOT_ASSESSED

    # "<1000", "500*", "500" — a numeric ceiling. The trailing * is a footnote
    # marker pointing at the specification reference, not part of the number.
    m = re.match(r"^[<≤]?\s*(\d+(?:\.\d+)?)\s*\*?$", spec)
    if not m:
        return ResultStatus.NOT_ASSESSED
    limit = float(m.group(1))

    if result.qualifier == "ND":
        return ResultStatus.PASS
    if result.value_num is None:
        return ResultStatus.NOT_ASSESSED
    if result.qualifier == "<":
        # "<0.5" against a limit of 0.5 proves nothing about the true value.
        return ResultStatus.PASS if result.value_num <= limit else ResultStatus.NOT_ASSESSED
    return ResultStatus.PASS if result.value_num <= limit else ResultStatus.FAIL


def bind_provenance(sample: LabSample) -> None:
    """Gate 5 — refuse any record that cannot say where it came from."""
    if not sample.source_sha256:
        raise GateFailure("no source_sha256 — the originating document is unidentifiable")
    if not sample.extraction_method:
        raise GateFailure("no extraction_method — how this was derived is unrecorded")
    if not sample.raw_extraction:
        raise GateFailure("no raw_extraction — gate 7 audit trail would be empty")


def apply(sample: LabSample) -> LabSample:
    """Run every gate over a freshly parsed sample and return it annotated.

    Always leaves `reviewer_status` at PENDING: in this system approval is a human
    act, so there is no path here that commits data on its own (gate 6).
    """
    bind_provenance(sample)                                     # gate 5

    sample.anomalies = check_consistency(sample)                # gate 3
    for result in sample.results:
        result.status = evaluate_printed_spec(result)

    if sample.anomalies:
        logger.warning("report %s flagged %d anomaly(ies): %s",
                       sample.report_no, len(sample.anomalies), "; ".join(sample.anomalies))
    if sample.extraction_confidence < CONFIDENCE_THRESHOLD:
        logger.info("report %s extracted at confidence %.2f — queued for review",
                    sample.report_no, sample.extraction_confidence)

    sample.reviewer_status = ReviewerStatus.PENDING             # gate 6
    return sample


def needs_human(sample: LabSample) -> bool:
    """True when a record must not be auto-approved even by a privileged caller."""
    return bool(sample.anomalies) or sample.extraction_confidence < CONFIDENCE_THRESHOLD


def failing_results(sample: LabSample) -> list[LabResult]:
    """Parameters that exceeded the limit printed on the report."""
    return [r for r in sample.results if r.status is ResultStatus.FAIL]
