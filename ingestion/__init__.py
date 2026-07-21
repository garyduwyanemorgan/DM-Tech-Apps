"""Lab-report ingestion — PDF in, validated structured data out.

Extraction produces a *hypothesis*, not data. Nothing here writes to a canonical
table on its own: `router.ingest()` returns a `LabSample` whose `reviewer_status`
starts at "pending", and a human approves it before it counts. See gates.py.
"""
from __future__ import annotations

from ingestion.schema import LabResult, LabSample, ResultStatus, ReviewerStatus

__all__ = ["LabResult", "LabSample", "ResultStatus", "ReviewerStatus"]
