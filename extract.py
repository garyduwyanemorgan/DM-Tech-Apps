"""Lab-report extraction — photo/PDF → structured water-quality readings.

Uses Claude vision to read a laboratory report image or PDF and return the 14
DECCA parameters as JSON. A human reviews/corrects the values before they are
saved (required for regulatory data) — this module only does the recognition.

Cost: one report is ~1-2K input tokens + a small JSON output — a fraction of a
cent. Model is configurable via LAB_EXTRACT_MODEL (default claude-haiku-4-5 —
fast and accurate for this OCR-style task; set claude-opus-4-8 if a report
proves too hard for it).

Images are downscaled/re-encoded before the API call: a 10MB phone photo adds
seconds of transfer + vision tokens for zero accuracy gain at lab-report text
sizes.

Requires the ANTHROPIC_API_KEY environment variable.
"""
from __future__ import annotations

import base64
import io
import os
from typing import Optional

from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-haiku-4-5"

# Longest side after downscale. 1568px is the max dimension Anthropic vision
# uses before resizing server-side anyway — larger uploads are pure waste.
_MAX_IMAGE_PX = 1568
_JPEG_QUALITY = 82

_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


class LabReadings(BaseModel):
    """The 14 DECCA water-quality parameters. Null where absent/unreadable."""
    ph:               Optional[float] = Field(None, description="pH (units)")
    do:               Optional[float] = Field(None, description="Dissolved oxygen, mg/L")
    tss:              Optional[float] = Field(None, description="Total suspended solids, mg/L")
    turbidity:        Optional[float] = Field(None, description="Turbidity, NTU")
    cod:              Optional[float] = Field(None, description="Chemical oxygen demand, mg/L")
    ammonia:          Optional[float] = Field(None, description="Ammonia as N, mg/L")
    phosphate:        Optional[float] = Field(None, description="Total phosphate, mg/L")
    oil_grease:       Optional[float] = Field(None, description="Oils & grease, mg/L")
    ecoli:            Optional[float] = Field(None, description="E. coli, CFU/100mL")
    total_coliforms:  Optional[float] = Field(None, description="Total coliforms, CFU/100mL")
    chla:             Optional[float] = Field(None, description="Chlorophyll-a, µg/L")
    phycocyanin:      Optional[float] = Field(None, description="Phycocyanin, µg/L")
    salinity:         Optional[float] = Field(None, description="Salinity, PSU")
    water_temp:       Optional[float] = Field(None, description="Water temperature, °C")
    notes:            Optional[str]   = Field(None, description="Any unreadable fields, "
                                              "unit mismatches, or values needing human check")


_PROMPT = (
    "You are reading a water-quality laboratory report for a Dubai lagoon. "
    "Extract the measured value for each of the listed parameters into the schema. "
    "Rules:\n"
    "- Return the numeric value only, in the unit named in the schema. If the report "
    "uses a different unit, convert it and note the conversion in `notes`.\n"
    "- Map common label variants: 'DO'/'Dissolved O2' → do; 'TSS'/'Suspended Solids' → tss; "
    "'COD' → cod; 'NH3'/'NH4'/'Ammoniacal N' → ammonia; 'PO4'/'Total P' → phosphate; "
    "'O&G'/'FOG' → oil_grease; 'E. coli' → ecoli; 'Total Coliform' → total_coliforms; "
    "'Chl-a'/'Chlorophyll a' → chla; 'Phycocyanin'/'PC' → phycocyanin; 'Temp' → water_temp.\n"
    "- If a parameter is absent or you cannot read it confidently, set it to null and say so "
    "in `notes`. Do NOT guess.\n"
    "- For values like '< 0.05' or 'ND', use the detection limit number and note it."
)


def is_configured() -> bool:
    """True when the API key + SDK are available."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _shrink_image(file_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """Downscale + re-encode an image for vision extraction.

    Returns (bytes, media_type) — the original pair if Pillow is unavailable
    or the image is already small. Never raises: extraction proceeds with the
    original bytes on any failure.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return file_bytes, media_type

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)  # phone photos carry rotation in EXIF
        needs_resize = max(img.size) > _MAX_IMAGE_PX
        # Re-encode anything over ~500KB even if dimensions are fine (huge
        # PNGs / low-compression JPEGs); below that the transfer win is noise.
        if not needs_resize and len(file_bytes) <= 500_000:
            return file_bytes, media_type
        if needs_resize:
            img.thumbnail((_MAX_IMAGE_PX, _MAX_IMAGE_PX), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return file_bytes, media_type


def extract_lab_report(file_bytes: bytes, media_type: str, model: str | None = None) -> dict:
    """Extract readings from a lab-report image or PDF. Returns a dict of the
    14 fields (+ notes). Raises with a clear message on failure."""
    import anthropic

    model = model or os.environ.get("LAB_EXTRACT_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY

    if media_type in _IMAGE_TYPES:
        file_bytes, media_type = _shrink_image(file_bytes, media_type)

    b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
    if media_type in _IMAGE_TYPES:
        mt = "image/jpeg" if media_type == "image/jpg" else media_type
        source_block = {"type": "image",
                        "source": {"type": "base64", "media_type": mt, "data": b64}}
    elif media_type == "application/pdf":
        source_block = {"type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        raise ValueError(f"Unsupported file type '{media_type}'. Upload an image or PDF.")

    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user",
                       "content": [source_block, {"type": "text", "text": _PROMPT}]}],
            output_format=LabReadings,
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("Invalid or missing ANTHROPIC_API_KEY.")
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Extraction service error ({exc.status_code}). Try again.")

    if resp.parsed_output is None:
        raise RuntimeError("Could not read the report. Try a clearer photo or enter manually.")
    return resp.parsed_output.model_dump()
