"""Supabase read/write helpers.

Table: readings
  id              bigserial PK
  site_name       text
  year            int
  month           int          1–12
  submitted_at    timestamptz
  ph              float
  do_mgl          float
  tss_mgl         float
  turbidity_ntu   float
  cod_mgl         float
  ammonia_mgl     float
  phosphate_mgl   float
  oil_grease_mgl  float
  ecoli_cfu       float
  total_coliforms_cfu float
  chla_ugl        float
  phycocyanin_ugl float
  salinity_psu    float
  water_temp_c    float
  UNIQUE(site_name, year, month)
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from .client import get_client


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row_to_reading(row: dict):
    """Convert a Supabase row dict to a WaterReading."""
    from core.models import WaterReading
    return WaterReading(
        timestamp=datetime(row["year"], row["month"], 15),
        ph=row["ph"],
        do=row["do_mgl"],
        tss=row["tss_mgl"],
        turbidity=row["turbidity_ntu"],
        cod=row["cod_mgl"],
        ammonia=row["ammonia_mgl"],
        phosphate=row["phosphate_mgl"],
        oil_grease=row["oil_grease_mgl"],
        ecoli=row["ecoli_cfu"],
        total_coliforms=row["total_coliforms_cfu"],
        chla=row["chla_ugl"],
        phycocyanin=row["phycocyanin_ugl"],
        salinity=row["salinity_psu"],
        water_temp=row["water_temp_c"],
    )


# ── Reads ─────────────────────────────────────────────────────────────────────

def get_readings_for_site(site_name: str, year: int | None = None) -> List:
    """Return WaterReading list ordered by month. Empty list on failure."""
    client = get_client()
    if not client:
        return []
    try:
        q = client.table("readings").select("*").eq("site_name", site_name)
        if year:
            q = q.eq("year", year)
        resp = q.order("year").order("month").execute()
        return [_row_to_reading(r) for r in (resp.data or [])]
    except Exception:
        return []


def get_site_names() -> List[str]:
    """Return configured site names.

    Resolved from, in order:
      1. Streamlit secrets  [site_passwords] keys   (Streamlit Cloud / local)
      2. Env var  LAGOON_SITES="Emaar,Damac,Nakheel" (Render / headless hosts)
    """
    # 1. Streamlit secrets
    try:
        import streamlit as st
        names = list(st.secrets.get("site_passwords", {}).keys())
        if names:
            return names
    except Exception:
        pass
    # 2. Environment variable
    import os
    raw = os.environ.get("LAGOON_SITES", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def reading_exists(site_name: str, year: int, month: int) -> bool:
    """True if a reading already exists for this site/year/month."""
    client = get_client()
    if not client:
        return False
    try:
        resp = (
            client.table("readings")
            .select("id")
            .eq("site_name", site_name)
            .eq("year", year)
            .eq("month", month)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        return False


# ── Writes ────────────────────────────────────────────────────────────────────

def insert_reading(
    site_name: str,
    year: int,
    month: int,
    fields: dict,
    upsert: bool = False,
) -> tuple[bool, str]:
    """Insert (or upsert) one monthly reading.

    Returns (success, message).
    fields keys: ph, do_mgl, tss_mgl, turbidity_ntu, cod_mgl, ammonia_mgl,
                 phosphate_mgl, oil_grease_mgl, ecoli_cfu, total_coliforms_cfu,
                 chla_ugl, phycocyanin_ugl, salinity_psu, water_temp_c
    """
    client = get_client()
    if not client:
        return False, "Supabase not configured."
    row = {"site_name": site_name, "year": year, "month": month, **fields}
    try:
        if upsert:
            client.table("readings").upsert(
                row, on_conflict="site_name,year,month"
            ).execute()
        else:
            client.table("readings").insert(row).execute()
        # Forward ledger: validate any open predictions for this site/month.
        try:
            validate_open_predictions(site_name, year, month, fields)
        except Exception:
            pass   # ledger is optional; never block a reading save
        return True, "Reading saved."
    except Exception as exc:
        msg = str(exc)
        if "duplicate key" in msg or "unique" in msg.lower():
            return False, "A reading for this site/month already exists. Enable overwrite to replace it."
        return False, f"Database error: {msg}"


# ── Predictions ledger (forward validation; table is optional) ───────────────

# Map a parameter key → the readings-table column holding its actual value.
_PARAM_TO_COLUMN = {
    "chla": "chla_ugl", "do": "do_mgl", "phosphate": "phosphate_mgl",
    "ammonia": "ammonia_mgl", "phycocyanin": "phycocyanin_ugl",
}


def insert_prediction(site_name: str, year: int, month: int, parameter: str,
                      predicted: float, band_low: float, band_high: float,
                      confidence_pct: float) -> bool:
    """Record a forward prediction. No-op (returns False) if table absent."""
    client = get_client()
    if not client:
        return False
    row = {
        "site_name": site_name, "year": year, "month": month, "parameter": parameter,
        "predicted": predicted, "band_low": band_low, "band_high": band_high,
        "confidence_pct": confidence_pct,
    }
    try:
        client.table("predictions").upsert(
            row, on_conflict="site_name,year,month,parameter").execute()
        return True
    except Exception:
        return False


def validate_open_predictions(site_name: str, year: int, month: int, fields: dict) -> int:
    """When a real reading lands, score any open predictions for it.
    `fields` is the readings-table row. Returns count validated. Safe no-op
    if the predictions table does not exist."""
    client = get_client()
    if not client:
        return 0
    try:
        resp = (client.table("predictions").select("*")
                .eq("site_name", site_name).eq("year", year).eq("month", month)
                .is_("actual", "null").execute())
        rows = resp.data or []
    except Exception:
        return 0
    n = 0
    for p in rows:
        col = _PARAM_TO_COLUMN.get(p["parameter"])
        if not col or col not in fields:
            continue
        actual = float(fields[col])
        within = p["band_low"] <= actual <= p["band_high"]
        abs_err = abs(actual - p["predicted"])
        pct_err = (abs_err / abs(actual) * 100.0) if actual else None
        try:
            client.table("predictions").update({
                "actual": actual, "within_band": within,
                "abs_error": round(abs_err, 4),
                "pct_error": round(pct_err, 2) if pct_err is not None else None,
                "validated_at": "now()",
            }).eq("id", p["id"]).execute()
            n += 1
        except Exception:
            continue
    return n


def get_validated_predictions(site_name: str | None = None) -> list:
    """Return validated prediction rows (actual filled). Empty if table absent."""
    client = get_client()
    if not client:
        return []
    try:
        q = client.table("predictions").select("*").not_.is_("actual", "null")
        if site_name:
            q = q.eq("site_name", site_name)
        return q.execute().data or []
    except Exception:
        return []
