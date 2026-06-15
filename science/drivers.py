"""Driver / forcing layer  —  INTERNAL, never surfaced client-facing.

External forcings that drive the causal chain, available WITHOUT sampling the
lagoon:
  • weather  — air temperature, solar radiation, wind, humidity, rainfall
               (live feed with offline climatology fallback)
  • inputs   — operator-supplied TSE inflow volume & source nutrient load

From these it derives the intermediate physical state the chain needs:
  • evaporation        (Priestley-Taylor, weather-only)
  • water temperature  (air temp + solar surplus)
  • salinity           (evaporative concentration above inflow baseline)

This module is the heart of the predictive moat — it lets the model run the
chain from free continuous data. Keep it out of any client-facing label/chart.
The weather vendor is an implementation detail and must not appear in the UI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from . import config


@dataclass
class Drivers:
    """External forcings for one lagoon-month."""
    year: int
    month: int                       # 1–12
    air_temp_c: float
    solar_kwh: float                 # kWh/m²/day
    wind_ms: float
    humidity_pct: float
    rainfall_mm: float
    source: str                      # "live" or "climatology" (internal only)
    # Operator inputs (optional)
    tse_inflow_m3_day: float = 0.0
    tse_phosphate_mgl: float = 0.0
    tse_nitrogen_mgl: float = 0.0


# ── Weather acquisition ───────────────────────────────────────────────────────

def _climatology(year: int, month: int) -> Drivers:
    i = month - 1
    c = config.CLIMATOLOGY
    return Drivers(
        year=year, month=month,
        air_temp_c=c["air_temp"][i], solar_kwh=c["solar"][i],
        wind_ms=c["wind"][i], humidity_pct=c["humidity"][i],
        rainfall_mm=c["rainfall"][i], source="climatology",
    )


def _fetch_live(year: int, month: int, timeout: float = 6.0) -> Optional[Drivers]:
    """Pull monthly-mean weather from the meteorological feed. Returns None on
    any failure so callers fall back to climatology. Vendor stays internal."""
    import json
    import urllib.request
    from calendar import monthrange
    from datetime import date

    last_day = monthrange(year, month)[1]
    start = date(year, month, 1).isoformat()
    end = date(year, month, last_day).isoformat()
    today = date.today()
    # Archive only covers the past; future/this-month months won't have data.
    if date(year, month, last_day) >= today:
        return None

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={config.DUBAI_LAT}&longitude={config.DUBAI_LON}"
        f"&start_date={start}&end_date={end}"
        "&daily=temperature_2m_mean,shortwave_radiation_sum,"
        "wind_speed_10m_max,relative_humidity_2m_mean,precipitation_sum"
        "&timezone=auto"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        d = data["daily"]

        def _mean(key):
            vals = [v for v in d.get(key, []) if v is not None]
            return sum(vals) / len(vals) if vals else None

        air = _mean("temperature_2m_mean")
        # shortwave_radiation_sum is MJ/m²/day → convert to kWh/m²/day
        rad_mj = _mean("shortwave_radiation_sum")
        solar = (rad_mj / config.SOLAR_KWH_TO_MJ) if rad_mj is not None else None
        wind = _mean("wind_speed_10m_max")
        hum = _mean("relative_humidity_2m_mean")
        rain_vals = [v for v in d.get("precipitation_sum", []) if v is not None]
        rain = sum(rain_vals) if rain_vals else 0.0

        if None in (air, solar, wind, hum):
            return None
        # wind comes in km/h from this endpoint → m/s
        wind_ms = wind / 3.6
        return Drivers(year=year, month=month, air_temp_c=air, solar_kwh=solar,
                       wind_ms=wind_ms, humidity_pct=hum, rainfall_mm=rain,
                       source="live")
    except Exception:
        return None


def get_drivers(year: int, month: int, use_live: bool = True) -> Drivers:
    """Return forcings for a lagoon-month: live feed if available, else
    climatology. Live/offline distinction is internal only."""
    if use_live:
        live = _fetch_live(year, month)
        if live is not None:
            return live
    return _climatology(year, month)


# ── Derived physical state (transparent equations) ───────────────────────────

def _sat_vapour_pressure(temp_c: float) -> float:
    """Saturation vapour pressure (kPa) — Tetens."""
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def _svp_slope(temp_c: float) -> float:
    """Slope Δ of the SVP curve (kPa/°C)."""
    es = _sat_vapour_pressure(temp_c)
    return 4098 * es / (temp_c + 237.3) ** 2


def evaporation_mm_day(d: Drivers) -> float:
    """Open-water evaporation (mm/day) via Priestley-Taylor — weather only.

    E = α · Δ/(Δ+γ) · Rn/λ
    with Rn ≈ PT_NET_RAD_FRACTION · incoming shortwave (MJ/m²/day).
    """
    delta = _svp_slope(d.air_temp_c)
    gamma = config.PT_PSYCHROMETRIC
    rn_mj = config.PT_NET_RAD_FRACTION * d.solar_kwh * config.SOLAR_KWH_TO_MJ
    e = config.PT_ALPHA * (delta / (delta + gamma)) * rn_mj / config.PT_LATENT_HEAT
    return max(0.0, round(e, 2))


def water_temperature(d: Drivers) -> float:
    """Lagoon water temperature (°C) from air temp + solar surplus."""
    solar_surplus = max(0.0, d.solar_kwh - config.WATERTEMP_SOLAR_REF)
    t = (config.WATERTEMP_AIR_COEF * d.air_temp_c
         + config.WATERTEMP_SOLAR_COEF * solar_surplus
         + config.WATERTEMP_OFFSET)
    return round(t, 1)


def salinity(d: Drivers, residence_days: float = 30.0) -> float:
    """Salinity (PSU) raised above the inflow baseline by evaporative
    concentration over the residence window (net of rainfall dilution)."""
    evap = evaporation_mm_day(d)
    rain_mm_day = d.rainfall_mm / 30.0
    net_evap = max(0.0, evap - rain_mm_day)
    # Longer residence → more accumulated concentration (scaled, saturating).
    window = min(residence_days, 120.0) / 30.0
    rise = config.SALINITY_EVAP_COEF * net_evap * window
    return round(config.SALINITY_BASELINE_PSU + rise, 1)


def derived_state(d: Drivers, residence_days: float = 30.0) -> dict:
    """Bundle the driver-derived physical state used by the predictor."""
    return {
        "evaporation_mm_day": evaporation_mm_day(d),
        "water_temp_c": water_temperature(d),
        "salinity_psu": salinity(d, residence_days),
    }
