"""Deterministic parser for Wimpey Laboratories test reports.

The client is under a multi-year contract with Wimpey, whose LIMS emits a stable
form (`Form No: WRF*-W-*`, Rev 00 since 2020). Those PDFs carry a real text layer
and ruled result tables, so this is a plain parse — no vision model. That matters
beyond cost: a regulator-facing number should be reproducible from the source
document, not resampled from a model each time.

Three form types are handled:

    WRF1-W-001  chemistry     — 24 params incl. heavy metals, LOQ column
    WRF2-W-001  microbiology  — 7 params, Specification + MOU columns
    WRF2-W-002  legionella    — enumeration + confirmatory identification

Layout notes that drive the implementation:

* The header is a two-column key/value block. Values wrap onto the *next line at
  their own column's x*, so reading in text order mis-assigns them — "Emirates"
  wraps under "Sample Location" but follows "Sampled By :Adnan" in the text
  stream. Everything here is therefore positional: cells are cut at label
  x-positions and continuation lines are re-attached by x-range.
* The governing standard is cited in free text under the results table, not in
  any column, and only on the two microbiological forms. See `_parse_standard`.
* The results table is genuinely ruled, so pdfplumber's `extract_tables()`
  recovers it cleanly. The first returned "table" is the header block (one merged
  cell) — the results table is the one whose first row starts with "Parameters".
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import date, datetime
from typing import Optional

from ingestion.schema import LabResult, LabSample

logger = logging.getLogger(__name__)

LABORATORY = "Wimpey Laboratories"

# Form No -> report type. Anything else is refused rather than guessed at.
FORM_TYPES: dict[str, str] = {
    "WRF1-W-001": "chemistry",
    "WRF2-W-001": "microbiology",
    "WRF2-W-002": "legionella",
}

# Header labels as printed. Order matters only for the longest-match-first regex
# below: "Analysis Start Date." must beat "Analysis" style prefixes, and
# "Sample No." must not be eaten by "Sample".
_LABELS = [
    "Report No.", "Request No.", "Received Date", "Sample No.",
    "Sampling Date", "Report Date.", "Analysis Start Date.", "Analysis End Date.",
    "Sample Location.", "Sampled By", "Sample Identification", "Sampling Method",
    "Temperature °C", "Source of Sample", "Sampling Point", "Sample Description",
    "Sampling Apparatus", "Sample volume", "Neutralizer", "Sampling Time",
    "Samplerrefno", "Mode of Transportation", "Preservation",
]
_LABEL_RE = re.compile(
    "(" + "|".join(re.escape(l) for l in sorted(_LABELS, key=len, reverse=True)) + r")\s*:?",
)

# Map printed label -> LabSample field.
_FIELD_MAP = {
    "Report No.": "report_no",
    "Sampling Point": "sampling_point",
    "Sample Location.": "sample_location",
    "Sample Identification": "sample_identification",
    "Source of Sample": "source_of_sample",
    "Sample Description": "sample_description",
    "Sampled By": "sampled_by",
    "Sampling Method": "sampling_method",
    "Sampling Apparatus": "sampling_apparatus",
    "Sample volume": "sample_volume",
    "Sampling Time": "sampling_time",
}
_DATE_MAP = {
    "Sampling Date": "sampled_at",
    "Received Date": "received_at",
    "Report Date.": "reported_at",
    "Analysis Start Date.": "analysis_start",
    "Analysis End Date.": "analysis_end",
}

_LINE_TOLERANCE = 3.0     # points; words within this share a visual line


class WimpeyParseError(ValueError):
    """The PDF is not a parseable Wimpey report."""


# ── low-level text geometry ──────────────────────────────────────────────────

def _cluster_lines(words: list[dict]) -> list[list[dict]]:
    """Group words into visual lines by `top`, tolerant of sub-point jitter."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= _LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(l, key=lambda w: w["x0"]) for l in lines]


def _parse_header(words: list[dict]) -> dict[str, str]:
    """Read the two/three-column key/value block into {printed label: value}.

    Each line is cut at the x-position of every label it contains, giving cells
    with a known x-range. A line containing no label is a wrapped continuation:
    each of its words is appended to the most recent cell whose x-range covers it.
    """
    fields: dict[str, str] = {}
    cells: list[dict] = []          # {label, x0, x1, parts}

    for line in _cluster_lines(words):
        text = " ".join(w["text"] for w in line)
        matches = list(_LABEL_RE.finditer(text))

        if not matches:
            # Continuation line — re-attach by column, newest matching cell wins.
            for w in line:
                for cell in reversed(cells):
                    if cell["x0"] <= w["x0"] < cell["x1"]:
                        cell["parts"].append(w["text"])
                        break
            continue

        # Cut the line into label-anchored cells. Locate each label's x by
        # walking the words, since regex offsets are into the joined string.
        starts: list[tuple[int, str]] = []
        cursor = 0
        for w in line:
            for m in matches:
                if m.start() == cursor:
                    starts.append((w["x0"], m.group(1)))
                    break
            cursor += len(w["text"]) + 1

        for i, (x0, label) in enumerate(starts):
            x1 = starts[i + 1][0] if i + 1 < len(starts) else 10_000.0
            # Keep the label words; they are stripped as a prefix below, which
            # handles multi-word labels that a per-word filter would leave behind.
            value_words = [w["text"] for w in line if x0 <= w["x0"] < x1]
            cells.append({"label": label, "x0": x0, "x1": x1, "parts": value_words})

    for cell in cells:
        raw = " ".join(cell["parts"])
        # Strip the printed label and its separating colon. The label may have been
        # split across words, so match on whitespace-tolerant label tokens.
        prefix = r"\s*".join(re.escape(tok) for tok in cell["label"].split())
        raw = re.sub(r"^\s*" + prefix + r"\s*", "", raw)
        raw = raw.lstrip(": ").strip()
        # "Mode of Transportation ... of Samples" — the label itself wraps.
        raw = re.sub(r"\s*of Samples\s*$", "", raw)
        if raw and cell["label"] not in fields:
            fields[cell["label"]] = re.sub(r"\s{2,}", " ", raw)
    return fields


def _to_date(value: str) -> Optional[date]:
    """Wimpey prints dd/mm/yyyy throughout."""
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", value or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%d/%m/%Y").date()
    except ValueError:
        return None


def _to_float(value: str) -> Optional[float]:
    m = re.search(r"-?\d+(?:\.\d+)?", (value or "").replace(",", ""))
    return float(m.group(0)) if m else None


def _split_value(raw: str) -> tuple[Optional[float], Optional[str]]:
    """Split a printed result into (magnitude, qualifier).

    "<1" -> (1.0, "<") — the value is *below* 1, not equal to it; the qualifier
    carries that. "Not Detected"/"Absent" -> (None, "ND"): no magnitude was
    reported, and inventing one would be a claim the lab never made.
    """
    text = (raw or "").strip()
    if not text:
        return None, None
    if re.match(r"(?i)^(not\s*detected|nd|absent|nil)$", text):
        return None, "ND"
    m = re.match(r"^([<>≤≥])\s*(-?\d+(?:\.\d+)?)$", text)
    if m:
        return float(m.group(2)), m.group(1)
    return _to_float(text), None


# ── table ────────────────────────────────────────────────────────────────────

def _results_table(page) -> Optional[list[list]]:
    """The ruled table whose header row is the Parameters/Test Methods row."""
    for table in page.extract_tables():
        for i, row in enumerate(table):
            first = (row[0] or "").strip()
            if first.startswith("Parameters"):
                return table[i:]
    return None


def _parse_results(tables: list[list[list]]) -> list[LabResult]:
    """Turn ruled rows into LabResults, mapping whichever columns the form has."""
    results: list[LabResult] = []
    for table in tables:
        header = [(c or "").strip().lower() for c in table[0]]

        def col(*names: str) -> Optional[int]:
            for n in names:
                for i, h in enumerate(header):
                    if h.startswith(n):
                        return i
            return None

        i_param = col("parameters")
        i_method = col("test methods", "test method")
        i_unit = col("units", "unit")
        i_result = col("results", "result")
        i_spec = col("specification")
        i_mou = col("mou")
        i_loq = col("loq", "limit of")

        for row in table[1:]:
            def cell(idx: Optional[int]) -> str:
                if idx is None or idx >= len(row):
                    return ""
                return (row[idx] or "").replace("\n", " ").strip()

            name = cell(i_param)
            if not name or name.lower().startswith(("note", "remarks", "analyst")):
                continue
            # The sign-off block ("Analyst Reviewed By…" / "AMS RM None") is ruled
            # into the same table but spans one merged cell. A genuine parameter
            # always carries at least a method, unit or result alongside its name.
            if not any(cell(i) for i in (i_method, i_unit, i_result)):
                continue
            value_raw = cell(i_result)
            value_num, qualifier = _split_value(value_raw)
            results.append(LabResult(
                parameter=name,
                test_method=cell(i_method),
                unit=cell(i_unit),
                value_raw=value_raw,
                value_num=value_num,
                qualifier=qualifier,
                loq=_to_float(cell(i_loq)) if i_loq is not None else None,
                mou=cell(i_mou),
                specification=cell(i_spec),
            ))
    return results


# ── governing standard ───────────────────────────────────────────────────────
#
# Both microbiology and legionella forms cite the standard their limits come from,
# in a free-text footnote under the results table. The two forms introduce it
# differently ("Note : Specification Reference:" vs a bare "Specification:") and
# punctuate it differently ("; 2024." vs ";2024"), so the anchors are alternatives
# and the separators are tolerant. Nothing here is inferred: the chemistry form
# prints no citation at all and must come back empty rather than inheriting a
# plausible-looking standard from its siblings.
#
# The trailing anchor is the Remarks/Analyst block, which always follows.
_CITATION_RE = re.compile(
    r"(?m)^(?:Note\s*:\s*Specification\s+Reference|Specification)\s*:\s*$"
    r"(.*?)"
    r"(?=^\s*(?:Remarks\s*:|Analyst\s+Reviewed\s+By|Key\s+Words\s*:))",
    re.S,
)
# "DM-HSD-GU44-LCWS2". Hyphen-joined uppercase/digit groups after the DM prefix.
_STANDARD_CODE_RE = re.compile(r"\bDM(?:-[A-Z0-9]+)+\b")
# "GSO 149/2021" and "GSO149/2021" are the same standard printed two ways.
_GSO_RE = re.compile(r"\bGSO\s*(\d+\s*/\s*\d{4})\b")


def _parse_standard(text: str) -> dict[str, object]:
    """Pull the governing standard out of the certificate footer.

    Returns only the fields actually printed; every caller-facing default is empty.
    The laboratory delimits the citation with semicolons — authority; title; code;
    year — so the parts are located *relative to the code* rather than by matching
    the wording of any one title. That survives a retitled guideline, which a
    literal title regex would silently drop.
    """
    found: dict[str, object] = {}
    m = _CITATION_RE.search(text)
    if not m:
        return found

    block = re.sub(r"\s+", " ", m.group(1)).strip()
    if not block:
        return found
    found["standard_citation"] = block

    segments = block.split(";")
    code_at = next(
        (i for i, s in enumerate(segments) if _STANDARD_CODE_RE.search(s)), None)
    if code_at is not None:
        found["standard_code"] = _STANDARD_CODE_RE.search(segments[code_at]).group(0)
        if code_at >= 1:
            # Printed case is evidence, not noise: the microbiology form says
            # "water System" and the legionella form "Water System". Quoting a
            # standard back to a regulator means quoting it as issued.
            found["standard_title"] = segments[code_at - 1].strip()
        if code_at == 0:
            # The authority precedes the title, so with no room for both there is
            # no authority to claim.
            found["standard_authority"] = ""
        else:
            found["standard_authority"] = segments[0].strip().lstrip("*").strip()
        if code_at + 1 < len(segments):
            # Anchored at the start of the following segment so a year mentioned
            # later in the prose ("GSO 149/2021") cannot be mistaken for it.
            y = re.match(r"\s*(\d{4})", segments[code_at + 1])
            if y:
                found["standard_year"] = y.group(1)

    extra: list[str] = []
    for gso in _GSO_RE.findall(block):
        label = "GSO " + re.sub(r"\s+", "", gso)
        if label not in extra:      # printed twice on the microbiology form
            extra.append(label)
    if extra:
        found["additional_standards"] = extra

    for field, pattern in (
        ("test_procedure", r"Test\s+Procedure\s*:\s*([^,;.]+)"),
        ("medium_used", r"Medium\s+Used\s*:\s*([^\s,;]+)"),
        ("filtered_volume", r"Sample\s+Volume\s+filtered\s+is\s+(\d+(?:\.\d+)?\s*[^\s,;&]+)"),
        ("detection_limit", r"Detection\s+limit\s+is\s+(\d+(?:\.\d+)?\s*[^\s,;.]+)"),
    ):
        found_m = re.search(pattern, block, re.I)
        if found_m:
            found[field] = found_m.group(1).strip()
    return found


# ── public interface ─────────────────────────────────────────────────────────

def detect_form_type(text: str) -> Optional[str]:
    """Return the `Form No:` code if this looks like a Wimpey report."""
    m = re.search(r"Form No:\s*(\S+)", text)
    if not m:
        return None
    code = m.group(1).strip()
    return code if code in FORM_TYPES else None


def is_wimpey_report(pdf_bytes: bytes) -> bool:
    """True when the PDF has a text layer naming a known Wimpey form."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = " ".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return False
    return detect_form_type(text) is not None


def parse(pdf_bytes: bytes, filename: str = "") -> LabSample:
    """Parse a Wimpey PDF into a LabSample. Raises WimpeyParseError if it isn't one."""
    try:
        import pdfplumber
    except ImportError as exc:                          # pragma: no cover
        raise RuntimeError(
            "pdfplumber is not installed. Install it with 'pip install pdfplumber' "
            "(see requirements.txt)."
        ) from exc

    try:
        pdf_ctx = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:
        # Surface a clean domain error; the API turns this into a 415 rather than
        # leaking a pdfminer traceback to the person who uploaded the file.
        raise WimpeyParseError(f"Could not open the file as a PDF: {exc}") from exc

    with pdf_ctx as pdf:
        pages_text = [(p.extract_text() or "") for p in pdf.pages]
        full_text = "\n".join(pages_text)

        form_type = detect_form_type(full_text)
        if not form_type:
            raise WimpeyParseError(
                "Not a recognised Wimpey report: no known 'Form No:' code found. "
                f"Supported: {', '.join(sorted(FORM_TYPES))}."
            )

        first = pdf.pages[0]
        table = _results_table(first)
        # Header words are everything above the results table.
        cutoff = min((w["top"] for w in first.extract_words()
                      if w["text"].startswith("Parameters")), default=first.height)
        header_words = [w for w in first.extract_words() if w["top"] < cutoff]
        fields = _parse_header(header_words)

        tables = [table] if table else []
        results = _parse_results(tables)

    remarks = ""
    m = re.search(r"Remarks\s*:(.+?)(?:Analyst|Key Words|Signed for)", full_text, re.S)
    if m:
        remarks = re.sub(r"\s+", " ", m.group(1)).strip()

    analyst, reviewed_by = _parse_signoff(full_text)
    standard = _parse_standard(full_text)

    sample = LabSample(
        laboratory=LABORATORY,
        report_no=fields.get("Report No.", ""),
        form_type=form_type,
        report_type=FORM_TYPES[form_type],
        temperature_c=_to_float(fields.get("Temperature °C", "")),
        remarks=remarks,
        analyst=analyst,
        reviewed_by=reviewed_by,
        results=results,
        source_filename=filename,
        source_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        extraction_method="wimpey-pdf-text",
        extraction_confidence=1.0,      # deterministic parse, not a model estimate
        raw_extraction={"form_type": form_type, "header": fields, "text": full_text},
        **{field: fields.get(label, "") for label, field in _FIELD_MAP.items()
           if label != "Report No."},
        # Absent keys fall back to the schema defaults; a form that prints no
        # citation (chemistry) must stay empty rather than borrow one.
        **standard,
    )
    for label, field in _DATE_MAP.items():
        setattr(sample, field, _to_date(fields.get(label, "")))

    logger.info("parsed Wimpey %s report %s (%d parameters)",
                sample.report_type, sample.report_no, len(sample.results))
    return sample


def _parse_signoff(text: str) -> tuple[str, str]:
    """The Analyst / Reviewed By row printed under the results table."""
    m = re.search(r"Analyst\s+Reviewed By\s+Method Variation\s*\n(.+)", text)
    if not m:
        return "", ""
    parts = m.group(1).split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return (parts[0] if parts else ""), ""
