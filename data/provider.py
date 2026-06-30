"""Unified data access layer.

Wraps both live Supabase data and the static sample_data fallback.
UI pages import from here instead of directly from sample_data.

Active site is read from st.session_state["active_site"] so that UI
pages need no argument changes — they just change their import.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List

from core.models import SludgeZone, WaterReading

# Re-export static constants that never come from live data
from data.sample_data import (  # noqa: F401
    TREATMENT_CALENDAR,
    TEMP_SPECIES_DOMINANCE,
    get_solar_irradiance,
    get_sludge_zones,
)
import data.sample_data as _sample


# ── Internal helpers ──────────────────────────────────────────────────────────

def _active_site() -> str | None:
    try:
        import streamlit as st
        return st.session_state.get("active_site")
    except Exception:
        return None


def _user_session() -> tuple[str | None, str | None]:
    try:
        import streamlit as st
        return st.session_state.get("user_token"), st.session_state.get("user_org_id")
    except Exception:
        return None, None


def _merge_with_sample(live: List[WaterReading], year: int) -> List[WaterReading]:
    """Fill any missing months from live data with sample values."""
    sample = _sample.get_monthly_readings(year)
    by_month = {r.timestamp.month: r for r in live}
    return [by_month.get(m + 1, sample[m]) for m in range(12)]


# ── Public API (same signatures as sample_data) ───────────────────────────────

def get_monthly_readings(year: int = 2026) -> List[WaterReading]:
    """12 WaterReadings for the year. Live data where available, sample elsewhere."""
    site = _active_site()
    if site:
        try:
            from db.queries import get_readings_for_site
            token, org_id = _user_session()
            live = get_readings_for_site(site, year=year, organization_id=org_id, token=token)
            if live:
                return _merge_with_sample(live, year)
        except Exception:
            pass
    return _sample.get_monthly_readings(year)


def get_current_reading(month_index: int = 2) -> WaterReading:
    """Single 'current' reading. Uses live data for the given month if available."""
    return get_monthly_readings()[month_index]


def get_monthly_table(year: int = 2026) -> dict:
    """Raw dict-of-lists, same structure as sample_data.get_monthly_table()."""
    readings = get_monthly_readings(year)
    return {
        "ph":          [r.ph           for r in readings],
        "do":          [r.do           for r in readings],
        "tss":         [r.tss          for r in readings],
        "turbidity":   [r.turbidity    for r in readings],
        "cod":         [r.cod          for r in readings],
        "ammonia":     [r.ammonia      for r in readings],
        "phosphate":   [r.phosphate    for r in readings],
        "oil_grease":  [r.oil_grease   for r in readings],
        "ecoli":       [r.ecoli        for r in readings],
        "coliforms":   [r.total_coliforms for r in readings],
        "chla":        [r.chla         for r in readings],
        "phycocyanin": [r.phycocyanin  for r in readings],
        "salinity":    [r.salinity     for r in readings],
        "water_temp":  [r.water_temp   for r in readings],
    }


def is_live() -> bool:
    """True when the active site has at least one real reading in Supabase."""
    site = _active_site()
    if not site:
        return False
    try:
        from db.queries import get_readings_for_site
        token, org_id = _user_session()
        return bool(get_readings_for_site(site, organization_id=org_id, token=token))
    except Exception:
        return False
