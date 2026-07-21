"""Chooses how to read an uploaded report, then runs it through the gates.

Wimpey PDFs carry a text layer, so they parse deterministically. Older scanned
reports (the pre-contract lagoon results) have no text layer and fall back to the
Claude vision path in extract.py — which is a genuine estimate, so it is marked
low-confidence and always lands in the review queue.
"""
from __future__ import annotations

import hashlib
import logging

from ingestion import gates, wimpey
from ingestion.schema import LabResult, LabSample

logger = logging.getLogger(__name__)

# Vision output is a model's reading of an image, not a parse. Below the gate-6
# threshold by construction: a human confirms every one of these.
VISION_CONFIDENCE = 0.60

_PDF_MAGIC = b"%PDF"


def ingest(file_bytes: bytes, media_type: str, filename: str = "") -> LabSample:
    """Parse an uploaded lab report into a gated LabSample.

    Raises ValueError for unusable input and RuntimeError when the chosen
    extractor is unavailable (e.g. no Anthropic key for a scanned report).
    """
    if not file_bytes:
        raise ValueError("Empty upload.")

    is_pdf = file_bytes.startswith(_PDF_MAGIC) or "pdf" in (media_type or "").lower()

    if is_pdf and wimpey.is_wimpey_report(file_bytes):
        sample = wimpey.parse(file_bytes, filename)
        logger.info("routed %s to the Wimpey text parser", filename or "upload")
    else:
        sample = _vision_fallback(file_bytes, media_type, filename)
        logger.info("routed %s to the Claude vision fallback", filename or "upload")

    return gates.apply(sample)


def _vision_fallback(file_bytes: bytes, media_type: str, filename: str) -> LabSample:
    """Wrap extract.py's vision output in the same schema and provenance."""
    from extract import extract_lab_report, is_configured

    if not is_configured():
        raise RuntimeError(
            "This report has no text layer, so it needs AI extraction, but no "
            "Anthropic API key is configured. Set ANTHROPIC_API_KEY."
        )

    raw = extract_lab_report(file_bytes, media_type)
    readings = {k: v for k, v in raw.items() if k != "notes" and v is not None}

    return LabSample(
        laboratory="",                      # unknown until a human identifies it
        report_no=filename or f"scan-{hashlib.sha256(file_bytes).hexdigest()[:12]}",
        form_type="",
        report_type="scanned",
        remarks=str(raw.get("notes") or ""),
        results=[
            LabResult(parameter=name, value_raw=str(value), value_num=_as_float(value))
            for name, value in readings.items()
        ],
        source_filename=filename,
        source_sha256=hashlib.sha256(file_bytes).hexdigest(),
        extraction_method="claude-vision",
        extraction_confidence=VISION_CONFIDENCE,
        raw_extraction=raw,
    )


def _as_float(value: object) -> float | None:
    try:
        return float(value)          # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
