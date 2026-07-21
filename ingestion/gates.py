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

from ingestion.schema import (
    ComplianceStatus, LabResult, LabSample, ResultStatus, ReviewerStatus,
)

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


def evaluate_printed_spec(result: LabResult) -> tuple[ResultStatus, str]:
    """Compare a result against the specification *printed on the same report*.

    Deliberately not a compliance engine: it applies no Dubai Municipality rules
    and no SOP knowledge, it only reads the limit the laboratory itself stated.
    Anything it cannot interpret with certainty is NOT_ASSESSED — an unreadable
    limit must never silently read as a pass.

    Returns the verdict *and* a one-sentence reason for it. The reason is not
    decoration: the reviewer acting on a NOT_ASSESSED needs to know whether the
    certificate omitted a limit (chase the laboratory) or printed one we could not
    read (fix this function), and every such sentence says outright that it is not
    a pass, because that is the reading a hurried reviewer would otherwise infer.
    """
    spec = (result.specification or "").strip()
    printed = result.value_raw.strip() or "(blank)"

    if not spec or spec == "-":
        return ResultStatus.NOT_ASSESSED, (
            "No specification was printed on the certificate for this parameter, "
            "so compliance cannot be judged from this document — this is not a pass."
        )

    # "Zero" / "Absent" — any detection is a failure.
    if re.match(r"(?i)^(zero|absent|nil|not\s*detected)$", spec):
        if result.qualifier in ("ND", "<"):
            return ResultStatus.PASS, (
                f"Reported as '{printed}', meeting the printed requirement of "
                f"'{spec}' (nothing detected)."
            )
        if result.value_num is not None and result.value_num > 0:
            return ResultStatus.FAIL, (
                f"Reported {printed} {result.unit or ''}".rstrip() +
                f" where the certificate requires '{spec}' — organisms were "
                "detected when none are permitted."
            )
        return ResultStatus.NOT_ASSESSED, (
            f"The certificate requires '{spec}', but the reported result "
            f"'{printed}' could not be read as either a detection or a "
            "non-detection — this is not a pass."
        )

    # "<1000", "500*", "500" — a numeric ceiling. The trailing * is a footnote
    # marker pointing at the specification reference, not part of the number.
    m = re.match(r"^[<≤]?\s*(\d+(?:\.\d+)?)\s*\*?$", spec)
    if not m:
        return ResultStatus.NOT_ASSESSED, (
            f"The specification printed on the certificate ('{spec}') is not in a "
            "form this system can interpret; a reviewer must read it against the "
            "result by hand — this is not a pass."
        )
    limit = float(m.group(1))

    if result.qualifier == "ND":
        return ResultStatus.PASS, (
            f"Not detected, which is within the printed limit of {spec}."
        )
    if result.value_num is None:
        return ResultStatus.NOT_ASSESSED, (
            f"The certificate prints a limit of {spec}, but the reported result "
            f"'{printed}' carries no number to compare against it — this is not "
            "a pass."
        )
    if result.qualifier == "<":
        # "<0.5" against a limit of 0.5 proves nothing about the true value.
        if result.value_num <= limit:
            return ResultStatus.PASS, (
                f"Reported {printed}, which is within the printed limit of {spec}."
            )
        return ResultStatus.NOT_ASSESSED, (
            f"Reported {printed}, and the printed limit is {spec}: the result is "
            "only bounded above the limit, so it neither demonstrates compliance "
            "nor proves an exceedance — this is not a pass."
        )
    if result.value_num <= limit:
        return ResultStatus.PASS, (
            f"Reported {printed}, which is within the printed limit of {spec}."
        )
    return ResultStatus.FAIL, (
        f"Reported {printed}, which exceeds the printed limit of {spec}."
    )


def roll_up_status(results: list[LabResult]) -> ComplianceStatus:
    """Certificate-level verdict. Precedence: FAIL beats NOT_ASSESSED beats PASS.

    A certificate with no result rows at all is INCOMPLETE. That case is the whole
    reason this is not a simple `all(PASS)`: an empty list satisfies `all()`, and
    a parser that silently extracted nothing would otherwise report a clean bill
    of health for a document nobody has assessed.
    """
    if not results:
        return ComplianceStatus.INCOMPLETE
    if any(r.status is ResultStatus.FAIL for r in results):
        return ComplianceStatus.NON_COMPLIANT
    if any(r.status is ResultStatus.NOT_ASSESSED for r in results):
        return ComplianceStatus.INCOMPLETE
    return ComplianceStatus.COMPLIANT


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
        result.status, result.status_reason = evaluate_printed_spec(result)
    sample.overall_status = roll_up_status(sample.results)

    if sample.overall_status is not ComplianceStatus.COMPLIANT:
        logger.info("report %s rolls up to %s", sample.report_no,
                    sample.overall_status.value)
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
