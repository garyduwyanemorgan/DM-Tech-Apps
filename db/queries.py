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

def get_or_create_site_id(site_name: str, organization_id: str | None = None, token: str | None = None) -> str | None:
    """Resolve site name and organization ID to site UUID. Auto-creates site if missing."""
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        # Search for existing site
        res = client.table("sites").select("id").eq("organization_id", organization_id).execute()
        # Find matching name (or filter in postgres if needed, but eq is safer)
        # We can also do .eq("name", site_name)
        res = client.table("sites").select("id").eq("organization_id", organization_id).eq("name", site_name).execute()
        if res.data:
            return res.data[0]["id"]
        # Create site if it doesn't exist
        ins = client.table("sites").insert({"organization_id": organization_id, "name": site_name}).execute()
        if ins.data:
            return ins.data[0]["id"]
    except Exception:
        pass
    return None


def get_readings_for_site(site_name: str, year: int | None = None, organization_id: str | None = None, token: str | None = None) -> List:
    """Return WaterReading list ordered by month. Empty list on failure."""
    client = get_client()
    if not client:
        return []
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if site_id:
            q = client.table("readings").select("*").eq("site_id", site_id)
        else:
            q = client.table("readings").select("*").eq("site_name", site_name)
        if year:
            q = q.eq("year", year)
        resp = q.order("year").order("month").execute()
        return [_row_to_reading(r) for r in (resp.data or [])]
    except Exception:
        return []


def get_site_names(organization_id: str | None = None, token: str | None = None) -> List[str]:
    """Return configured site names.

    If organization_id is provided, queries the Supabase 'sites' table.
    Otherwise, falls back to:
      1. Streamlit secrets  [site_passwords] keys   (Streamlit Cloud / local)
      2. Env var  LAGOON_SITES="Emaar,Damac,Nakheel" (Render / headless hosts)
    """
    client = get_client()
    if client and organization_id:
        try:
            res = client.table("sites").select("name").eq("organization_id", organization_id).execute()
            if res.data:
                return [row["name"] for row in res.data]
        except Exception:
            pass

    # ── Fallbacks ──
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


def reading_exists(site_name: str, year: int, month: int, organization_id: str | None = None, token: str | None = None) -> bool:
    """True if a reading already exists for this site/year/month."""
    client = get_client()
    if not client:
        return False
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if site_id:
            q = client.table("readings").select("id").eq("site_id", site_id).eq("year", year).eq("month", month)
        else:
            q = client.table("readings").select("id").eq("site_name", site_name).eq("year", year).eq("month", month)
        resp = q.execute()
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
    organization_id: str | None = None,
    token: str | None = None,
) -> tuple[bool, str]:
    """Insert (or upsert) one monthly reading.

    Returns (success, message).
    """
    client = get_client()
    if not client:
        return False, "Supabase not configured."
    
    site_id = get_or_create_site_id(site_name, organization_id, token)
    row = {"site_name": site_name, "year": year, "month": month, **fields}
    if site_id:
        row["site_id"] = site_id

    try:
        if upsert:
            conflict_cols = "site_id,year,month" if site_id else "site_name,year,month"
            client.table("readings").upsert(
                row, on_conflict=conflict_cols
            ).execute()
        else:
            client.table("readings").insert(row).execute()
        # Forward ledger: validate any open predictions for this site/month.
        try:
            validate_open_predictions(site_name, year, month, fields, organization_id, token)
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
                      confidence_pct: float, organization_id: str | None = None,
                      token: str | None = None) -> bool:
    """Record a forward prediction. No-op (returns False) if table absent."""
    client = get_client()
    if not client:
        return False
    
    site_id = get_or_create_site_id(site_name, organization_id, token)
    row = {
        "site_name": site_name, "year": year, "month": month, "parameter": parameter,
        "predicted": predicted, "band_low": band_low, "band_high": band_high,
        "confidence_pct": confidence_pct,
    }
    if site_id:
        row["site_id"] = site_id

    try:
        conflict_cols = "site_id,year,month,parameter" if site_id else "site_name,year,month,parameter"
        client.table("predictions").upsert(
            row, on_conflict=conflict_cols).execute()
        return True
    except Exception:
        return False


def validate_open_predictions(site_name: str, year: int, month: int, fields: dict,
                              organization_id: str | None = None, token: str | None = None) -> int:
    """When a real reading lands, score any open predictions for it."""
    client = get_client()
    if not client:
        return 0
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if site_id:
            resp = (client.table("predictions").select("*")
                    .eq("site_id", site_id).eq("year", year).eq("month", month)
                    .is_("actual", "null").execute())
        else:
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


def get_validated_predictions(site_name: str | None = None, organization_id: str | None = None,
                               token: str | None = None) -> list:
    """Return validated prediction rows (actual filled). Empty if table absent."""
    client = get_client()
    if not client:
        return []
    try:
        q = client.table("predictions").select("*").not_.is_("actual", "null")
        if site_name:
            site_id = get_or_create_site_id(site_name, organization_id, token)
            if site_id:
                q = q.eq("site_id", site_id)
            else:
                q = q.eq("site_name", site_name)
        return q.execute().data or []
    except Exception:
        return []


# ── Tenant provisioning helpers ──

def create_organization(name: str, token: str | None = None) -> str | None:
    """Create a tenant organization and return its UUID.

    Sets billing defaults explicitly (Starter plan, 1 site) so the row is always
    valid even when the DB column defaults were never applied — billing_status
    does arithmetic on site_limit and would raise on a NULL.
    """
    client = get_client()
    if not client:
        return None
    try:
        res = client.table("organizations").insert({
            "name": name,
            "plan_name": "starter",
            "site_limit": 1,
        }).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        # Billing columns may not exist yet (001_billing.sql not applied) —
        # retry name-only so org creation still succeeds.
        try:
            res = client.table("organizations").insert({"name": name}).execute()
            if res.data:
                return res.data[0]["id"]
        except Exception:
            pass
    return None


def create_site(organization_id: str, name: str, volume_m3: float = 0.0,
                salinity_baseline: float = 45.0, token: str | None = None) -> str | None:
    """Create a dynamic site for an organization and return its UUID."""
    # Use service role client — authenticated role lacks INSERT on sites.
    # organization_id is already validated from the user's JWT in the API layer.
    client = get_client()
    if not client:
        return None
    try:
        res = client.table("sites").insert({
            "organization_id": organization_id,
            "name": name,
            "volume_m3": volume_m3,
            "salinity_baseline": salinity_baseline,
        }).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return None


def delete_site(site_name: str, organization_id: str | None = None, token: str | None = None) -> tuple[bool, str, int]:
    """Delete a site and ALL associated readings/predictions.

    Returns (success, message, readings_deleted).
    """
    # Use service role client for cascade deletes — authenticated role lacks DELETE.
    client = get_client()
    if not client:
        return False, "Supabase not configured.", 0
    try:
        q = client.table("sites").select("id").eq("name", site_name)
        if organization_id:
            q = q.eq("organization_id", organization_id)
        res = q.execute()
        if not res.data:
            return False, f"Site '{site_name}' not found.", 0
        site_id = res.data[0]["id"]

        # Count readings before deletion
        count_res = client.table("readings").select("id", count="exact").eq("site_id", site_id).execute()
        reading_count = count_res.count or 0

        # Delete readings
        client.table("readings").delete().eq("site_id", site_id).execute()
        # Also cover legacy rows stored by site_name only
        client.table("readings").delete().eq("site_name", site_name).execute()

        # Delete predictions (table may not exist — silently ignore)
        try:
            client.table("predictions").delete().eq("site_id", site_id).execute()
        except Exception:
            pass

        # Delete the site record itself
        client.table("sites").delete().eq("id", site_id).execute()

        return True, f"Site '{site_name}' and {reading_count} reading(s) deleted.", reading_count
    except Exception as exc:
        return False, f"Database error: {str(exc)}", 0


def get_site_reading_count(site_name: str, organization_id: str | None = None, token: str | None = None) -> int:
    """Return the number of readings stored for a site."""
    client = get_client()
    if not client:
        return 0
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if site_id:
            res = client.table("readings").select("id", count="exact").eq("site_id", site_id).execute()
        else:
            res = client.table("readings").select("id", count="exact").eq("site_name", site_name).execute()
        return res.count or 0
    except Exception:
        return 0

