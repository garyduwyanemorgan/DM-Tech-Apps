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
    # 1. Local secrets.toml [site_passwords] — one entry per client site
    from core.config import secret_block
    names = list(secret_block("site_passwords").keys())
    if names:
        return names
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
                salinity_baseline: float = 45.0, address: str | None = None,
                token: str | None = None) -> str | None:
    """Create a dynamic site for an organization and return its UUID."""
    # Use service role client — authenticated role lacks INSERT on sites.
    # organization_id is already validated from the user's JWT in the API layer.
    client = get_client()
    if not client:
        return None
    try:
        row = {
            "organization_id": organization_id,
            "name": name,
            "volume_m3": volume_m3,
            "salinity_baseline": salinity_baseline,
        }
        if address:
            # address column arrives with migration 015; only sent when set so
            # an unapplied migration doesn't break address-less creates.
            row["address"] = address
        res = client.table("sites").insert(row).execute()
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


# ── Sludge & sediment surveys ────────────────────────────────────────────────

# Depth columns may be named *_m (post-metric-rename) or the original *_ft; the
# VALUES are always metres. Detect once which pair the table actually has so the
# feature works whether or not migration 004 has been applied.
_SLUDGE_DEPTH_COLS: tuple[str, str] | None = None


def _sludge_depth_cols(client) -> tuple[str, str]:
    """Return (total_col, sludge_col) — whichever naming the table currently uses."""
    global _SLUDGE_DEPTH_COLS
    if _SLUDGE_DEPTH_COLS:
        return _SLUDGE_DEPTH_COLS
    for total_col, sludge_col in (("total_depth_m", "sludge_depth_m"),
                                  ("total_depth_ft", "sludge_depth_ft")):
        try:
            client.table("sludge_surveys").select(total_col).limit(1).execute()
            _SLUDGE_DEPTH_COLS = (total_col, sludge_col)
            return _SLUDGE_DEPTH_COLS
        except Exception:
            continue
    _SLUDGE_DEPTH_COLS = ("total_depth_m", "sludge_depth_m")
    return _SLUDGE_DEPTH_COLS


def _zone_with_metrics(row: dict) -> dict:
    """Attach derived capacity metrics to a raw sludge_surveys row. Depths in metres."""
    total = row.get("total_depth_m") or row.get("total_depth_ft") or 0.0
    sludge = row.get("sludge_depth_m") or row.get("sludge_depth_ft") or 0.0
    effective = total - sludge
    loss_pct = (sludge / total * 100.0) if total else 0.0
    status = "CRITICAL" if loss_pct > 30 else "WARNING" if loss_pct > 20 else "OK"
    return {
        "zone_name": row.get("zone_name", ""),
        "total_depth_m": total,
        "sludge_depth_m": sludge,
        "effective_depth_m": round(effective, 2),
        "capacity_loss_pct": round(loss_pct, 1),
        "status": status,
        "survey_date": str(row.get("survey_date") or ""),
    }


def get_sludge_zones(site_name: str, organization_id: str | None = None,
                     token: str | None = None) -> List[dict]:
    """Return the sludge survey zones for a site, each with derived metrics.
    Empty list if the table is absent, the site is unknown, or on any error."""
    client = get_client()
    if not client:
        return []
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if not site_id:
            return []
        res = (client.table("sludge_surveys").select("*")
               .eq("site_id", site_id).order("zone_name").execute())
        return [_zone_with_metrics(r) for r in (res.data or [])]
    except Exception:
        return []


def upsert_sludge_zone(site_name: str, zone_name: str, total_depth_m: float,
                       sludge_depth_m: float, survey_date: str | None = None,
                       organization_id: str | None = None,
                       token: str | None = None) -> tuple[bool, str]:
    """Insert or update one sludge zone for a site (keyed on site_id + zone_name).
    Depths in metres. Returns (success, message)."""
    client = get_client()
    if not client:
        return False, "Supabase not configured."
    site_id = get_or_create_site_id(site_name, organization_id, token)
    if not site_id:
        return False, "Site not found for this organization."
    total_col, sludge_col = _sludge_depth_cols(client)
    row = {
        "site_id": site_id,
        "zone_name": zone_name,
        total_col: total_depth_m,   # value is metres regardless of column name
        sludge_col: sludge_depth_m,
    }
    if survey_date:
        row["survey_date"] = survey_date
    try:
        client.table("sludge_surveys").upsert(row, on_conflict="site_id,zone_name").execute()
        return True, "Zone saved."
    except Exception as exc:
        msg = str(exc)
        if "sludge_surveys" in msg and ("does not exist" in msg or "not find the table" in msg.lower()):
            return False, "Sludge table not found — run migration 003_sludge_surveys.sql in Supabase."
        return False, f"Database error: {msg}"


def delete_sludge_zone(site_name: str, zone_name: str, organization_id: str | None = None,
                       token: str | None = None) -> tuple[bool, str]:
    """Delete one sludge zone from a site. Returns (success, message)."""
    client = get_client()
    if not client:
        return False, "Supabase not configured."
    site_id = get_or_create_site_id(site_name, organization_id, token)
    if not site_id:
        return False, "Site not found for this organization."
    try:
        res = (client.table("sludge_surveys").delete()
               .eq("site_id", site_id).eq("zone_name", zone_name).execute())
        if not res.data:
            return False, f"Zone '{zone_name}' not found."
        return True, f"Zone '{zone_name}' deleted."
    except Exception as exc:
        return False, f"Database error: {str(exc)}"


# ── Data & lab requests ──────────────────────────────────────────────────────

def create_data_request(site_name: str, items: List[str], reason: str = "",
                        organization_id: str | None = None,
                        token: str | None = None) -> tuple[bool, str, dict | None]:
    """Persist an open data/lab request for a site. Returns (ok, message, row)."""
    client = get_client()
    if not client:
        return False, "Supabase not configured.", None
    site_id = get_or_create_site_id(site_name, organization_id, token)
    if not site_id:
        return False, "Site not found for this organization.", None
    if not items:
        return False, "Nothing to request — no items supplied.", None
    try:
        res = client.table("data_requests").insert({
            "site_id": site_id, "items": items, "reason": reason, "status": "open",
        }).execute()
        row = res.data[0] if res.data else None
        return True, "Request created.", row
    except Exception as exc:
        msg = str(exc)
        if "data_requests" in msg and ("does not exist" in msg or "not find the table" in msg.lower()):
            return False, "Requests table not found — run migration 005_data_requests.sql in Supabase.", None
        return False, f"Database error: {msg}", None


def get_open_data_requests(site_name: str, organization_id: str | None = None,
                          token: str | None = None) -> List[dict]:
    """Return open data/lab requests for a site (newest first). [] if none/absent."""
    client = get_client()
    if not client:
        return []
    try:
        site_id = get_or_create_site_id(site_name, organization_id, token)
        if not site_id:
            return []
        res = (client.table("data_requests").select("*")
               .eq("site_id", site_id).eq("status", "open")
               .order("created_at", desc=True).execute())
        return res.data or []
    except Exception:
        return []


def dismiss_data_request(request_id: str, site_name: str,
                        organization_id: str | None = None,
                        token: str | None = None) -> tuple[bool, str]:
    """Mark a request fulfilled (scoped to the site's organization)."""
    client = get_client()
    if not client:
        return False, "Supabase not configured."
    site_id = get_or_create_site_id(site_name, organization_id, token)
    if not site_id:
        return False, "Site not found for this organization."
    try:
        res = (client.table("data_requests").update({"status": "fulfilled"})
               .eq("id", request_id).eq("site_id", site_id).execute())
        if not res.data:
            return False, "Request not found."
        return True, "Request marked fulfilled."
    except Exception as exc:
        return False, f"Database error: {str(exc)}"



# ── Scope: user -> site / project assignments (migration 007) ─────────────────
# These back Phase 2 scope enforcement. They fail safe: if the assignment tables
# do not exist yet (migration unapplied) or the DB is down, reads return empty and
# writes return False, so nothing crashes — enforcement stays behind the
# SCOPE_ENFORCEMENT flag until backfill is complete.

def get_assigned_site_ids(user_clerk_id: str, organization_id: str) -> list[str]:
    """Site ids explicitly assigned to a user within an org (Site Supervisor scope)."""
    client = get_client()
    if not client or not user_clerk_id or not organization_id:
        return []
    try:
        res = (client.table("user_site_assignments").select("site_id")
               .eq("user_clerk_id", user_clerk_id)
               .eq("organization_id", organization_id).execute())
        return [r["site_id"] for r in (res.data or [])]
    except Exception:
        return []


def get_project_site_ids(user_clerk_id: str, organization_id: str) -> list[str]:
    """Site ids belonging to the projects a user is assigned to (Project Manager scope)."""
    client = get_client()
    if not client or not user_clerk_id or not organization_id:
        return []
    try:
        pa = (client.table("user_project_assignments").select("project_id")
              .eq("user_clerk_id", user_clerk_id)
              .eq("organization_id", organization_id).execute())
        project_ids = [r["project_id"] for r in (pa.data or [])]
        if not project_ids:
            return []
        sr = (client.table("sites").select("id")
              .eq("organization_id", organization_id)
              .in_("project_id", project_ids).execute())
        return [r["id"] for r in (sr.data or [])]
    except Exception:
        return []


def list_user_site_assignments(user_clerk_id: str, organization_id: str) -> list[str]:
    """Alias for get_assigned_site_ids, for the assignment-admin read endpoint."""
    return get_assigned_site_ids(user_clerk_id, organization_id)


def set_user_site_assignments(user_clerk_id: str, site_ids: list[str],
                              organization_id: str, assigned_by: str | None = None) -> tuple[bool, str]:
    """Replace a user's site assignments with the given set (scoped to the org).

    Only assigns sites that actually belong to the org (server-side validation —
    never trust caller-supplied ids). Returns (ok, message).
    """
    client = get_client()
    if not client or not user_clerk_id or not organization_id:
        return False, "Supabase not configured."
    try:
        # Validate the requested sites are in this org.
        valid = (client.table("sites").select("id")
                 .eq("organization_id", organization_id)
                 .in_("id", site_ids or [""]).execute())
        valid_ids = {r["id"] for r in (valid.data or [])}
        # Clear existing, then insert the validated set.
        (client.table("user_site_assignments").delete()
         .eq("user_clerk_id", user_clerk_id)
         .eq("organization_id", organization_id).execute())
        rows = [{
            "user_clerk_id": user_clerk_id, "site_id": sid,
            "organization_id": organization_id, "assigned_by": assigned_by,
        } for sid in valid_ids]
        if rows:
            client.table("user_site_assignments").insert(rows).execute()
        skipped = len(set(site_ids or [])) - len(valid_ids)
        msg = f"Assigned {len(valid_ids)} site(s)."
        if skipped > 0:
            msg += f" Skipped {skipped} not in this organization."
        return True, msg
    except Exception as exc:
        return False, f"Database error: {str(exc)}"


# ── Demo mode (migration 014) ─────────────────────────────────────────────────
# One server-provisioned demo key per organization. Fail-safe: if the table is
# missing or the DB is down, reads return None — no key means no demo and no
# expired-demo block, so nothing locks up.

def get_demo_key(organization_id: str) -> dict | None:
    """The org's demo key row (key_code, activated_at, expires_at), or None."""
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        res = (client.table("demo_keys")
               .select("key_code, activated_by, activated_at, expires_at")
               .eq("organization_id", organization_id).limit(1).execute())
        return (res.data or [None])[0]
    except Exception:
        return None


def create_demo_key(organization_id: str, activated_by: str | None) -> tuple[dict | None, str]:
    """Provision + activate the org's demo key (one per org, ever).

    Returns (row, message); row is None on failure. The UNIQUE(organization_id)
    constraint makes double-activation race-safe.
    """
    from datetime import datetime, timezone
    from core.demo import demo_expiry, generate_demo_key
    client = get_client()
    if not client or not organization_id:
        return None, "Database not available."
    now = datetime.now(timezone.utc)
    row = {
        "organization_id": organization_id,
        "key_code": generate_demo_key(),
        "activated_by": activated_by,
        "activated_at": now.isoformat(),
        "expires_at": demo_expiry(now).isoformat(),
    }
    try:
        res = client.table("demo_keys").insert(row).execute()
        if res.data:
            return res.data[0], "Demo activated."
        return None, "Failed to activate demo."
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            return None, "This organisation has already used its demo."
        return None, f"Database error: {str(exc)}"


# ── Corrective actions (migration 008) ────────────────────────────────────────
# Org-scoped workflow with an append-only event history. All writes go through the
# service-role client; callers enforce permission + state-machine rules first.

def create_corrective_action(organization_id: str, fields: dict, actor_clerk_id: str | None = None) -> dict | None:
    """Insert a corrective action (status 'open') and its 'created' event. Returns the row."""
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        row = {k: v for k, v in fields.items() if v is not None}
        row["organization_id"] = organization_id
        row["created_by"] = actor_clerk_id
        res = client.table("corrective_actions").insert(row).execute()
        if not res.data:
            return None
        action = res.data[0]
        client.table("corrective_action_events").insert({
            "action_id": action["id"], "organization_id": organization_id,
            "event_type": "created", "to_status": "open",
            "actor_clerk_id": actor_clerk_id,
            "note": fields.get("title"),
        }).execute()
        return action
    except Exception:
        return None


def list_corrective_actions(organization_id: str, site_id: str | None = None,
                            status: str | None = None) -> list[dict]:
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        q = client.table("corrective_actions").select("*").eq("organization_id", organization_id)
        if site_id:
            q = q.eq("site_id", site_id)
        if status:
            q = q.eq("status", status)
        return (q.order("created_at", desc=True).execute().data) or []
    except Exception:
        return []


def get_corrective_action(organization_id: str, action_id: str) -> dict | None:
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        res = (client.table("corrective_actions").select("*")
               .eq("id", action_id).eq("organization_id", organization_id).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def transition_corrective_action(organization_id: str, action_id: str, to_status: str,
                                 from_status: str, actor_clerk_id: str | None = None,
                                 note: str | None = None, evidence_url: str | None = None) -> tuple[bool, str]:
    """Update an action's status and append an immutable event. Assumes the caller
    already validated the transition is legal and permitted."""
    client = get_client()
    if not client or not organization_id:
        return False, "Supabase not configured."
    try:
        updates = {"status": to_status}
        if to_status in ("closed", "cancelled"):
            updates["closed_by"] = actor_clerk_id
            updates["closed_at"] = "now()"
        res = (client.table("corrective_actions").update(updates)
               .eq("id", action_id).eq("organization_id", organization_id).execute())
        if not res.data:
            return False, "Action not found."
        client.table("corrective_action_events").insert({
            "action_id": action_id, "organization_id": organization_id,
            "event_type": "status_change", "from_status": from_status, "to_status": to_status,
            "actor_clerk_id": actor_clerk_id, "note": note, "evidence_url": evidence_url,
        }).execute()
        return True, f"Action moved to {to_status}."
    except Exception as exc:
        return False, f"Database error: {str(exc)}"


def get_corrective_action_events(organization_id: str, action_id: str) -> list[dict]:
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        return (client.table("corrective_action_events").select("*")
                .eq("organization_id", organization_id).eq("action_id", action_id)
                .order("created_at").execute().data) or []
    except Exception:
        return []


# ── Inventory (migrations 009 + 011) ──────────────────────────────────────────
# Balances are SUM(qty_delta) over the append-only ledger. Consumption and
# transfers go through the Postgres RPCs (record_consumption/record_transfer) so
# the check-and-insert is atomic under concurrency; receipts/adjustments are plain
# signed ledger inserts. Financial fields are stripped by the API layer unless the
# caller holds inventory.valuation.read.

def create_inventory_item(organization_id: str, fields: dict) -> dict | None:
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        row = {k: v for k, v in fields.items() if v is not None}
        row["organization_id"] = organization_id
        res = client.table("inventory_items").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def create_inventory_location(organization_id: str, fields: dict) -> dict | None:
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        row = {k: v for k, v in fields.items() if v is not None}
        row["organization_id"] = organization_id
        res = client.table("inventory_locations").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def list_inventory_items(organization_id: str) -> list[dict]:
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        return (client.table("inventory_items").select("*")
                .eq("organization_id", organization_id).order("name").execute().data) or []
    except Exception:
        return []


def get_ledger_rows(organization_id: str, item_id: str | None = None) -> list[dict]:
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        q = client.table("inventory_ledger").select("*").eq("organization_id", organization_id)
        if item_id:
            q = q.eq("item_id", item_id)
        return q.execute().data or []
    except Exception:
        return []


def record_receipt(organization_id: str, item_id: str, location_id: str, qty: float,
                   batch_id: str | None = None, actor_clerk_id: str | None = None,
                   reason: str | None = None) -> tuple[bool, str]:
    """Receive stock: a positive ledger row (no balance check needed)."""
    client = get_client()
    if not client or not organization_id:
        return False, "Supabase not configured."
    if qty is None or qty <= 0:
        return False, "Receipt quantity must be positive."
    try:
        client.table("inventory_ledger").insert({
            "organization_id": organization_id, "item_id": item_id, "location_id": location_id,
            "batch_id": batch_id, "txn_type": "receive", "qty_delta": qty,
            "reason": reason, "actor_clerk_id": actor_clerk_id,
        }).execute()
        return True, "Stock received."
    except Exception as exc:
        return False, f"Database error: {str(exc)}"


def record_adjustment(organization_id: str, item_id: str, location_id: str, qty_delta: float,
                      reason: str, batch_id: str | None = None,
                      actor_clerk_id: str | None = None) -> tuple[bool, str]:
    """Correct a balance with a signed adjustment row and a mandatory reason."""
    client = get_client()
    if not client or not organization_id:
        return False, "Supabase not configured."
    if not reason:
        return False, "Adjustments require a reason."
    try:
        client.table("inventory_ledger").insert({
            "organization_id": organization_id, "item_id": item_id, "location_id": location_id,
            "batch_id": batch_id, "txn_type": "adjust", "qty_delta": qty_delta,
            "reason": reason, "actor_clerk_id": actor_clerk_id,
        }).execute()
        return True, "Adjustment recorded."
    except Exception as exc:
        return False, f"Database error: {str(exc)}"


def rpc_consume(organization_id: str, item_id: str, location_id: str, qty: float,
                batch_id: str | None = None, actor_clerk_id: str | None = None,
                ref_site_id: str | None = None, ref_action_id: str | None = None,
                reason: str | None = None) -> tuple[bool, str, float | None]:
    """Atomic consume via the record_consumption RPC. Returns (ok, msg, new_balance)."""
    client = get_client()
    if not client or not organization_id:
        return False, "Supabase not configured.", None
    try:
        res = client.rpc("record_consumption", {
            "p_org": organization_id, "p_item": item_id, "p_location": location_id,
            "p_qty": qty, "p_batch": batch_id, "p_actor": actor_clerk_id,
            "p_ref_site": ref_site_id, "p_ref_action": ref_action_id, "p_reason": reason,
        }).execute()
        return True, "Consumption recorded.", res.data
    except Exception as exc:
        msg = str(exc)
        if "insufficient stock" in msg:
            return False, "Insufficient stock for this consumption.", None
        return False, f"Database error: {msg[:120]}", None


def rpc_transfer(organization_id: str, item_id: str, from_location_id: str, to_location_id: str,
                 qty: float, batch_id: str | None = None, actor_clerk_id: str | None = None,
                 reason: str | None = None) -> tuple[bool, str]:
    """Atomic transfer via the record_transfer RPC."""
    client = get_client()
    if not client or not organization_id:
        return False, "Supabase not configured."
    try:
        client.rpc("record_transfer", {
            "p_org": organization_id, "p_item": item_id, "p_from": from_location_id,
            "p_to": to_location_id, "p_qty": qty, "p_batch": batch_id,
            "p_actor": actor_clerk_id, "p_reason": reason,
        }).execute()
        return True, "Stock transferred."
    except Exception as exc:
        msg = str(exc)
        if "insufficient stock" in msg:
            return False, "Insufficient stock at source location."
        if "differ" in msg:
            return False, "Source and destination must differ."
        return False, f"Database error: {msg[:120]}"


# ── Assets & maintenance (migration 010) ──────────────────────────────────────

def create_asset(organization_id: str, fields: dict) -> dict | None:
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        row = {k: v for k, v in fields.items() if v is not None}
        row["organization_id"] = organization_id
        res = client.table("assets").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


def list_assets(organization_id: str, site_id: str | None = None,
                asset_class: str | None = None) -> list[dict]:
    """Assets for an organisation, optionally narrowed by site and/or class.

    The upload flow asks for `asset_class='sampled'` — a laboratory certificate is
    never about a dosing pump.
    """
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        q = client.table("assets").select("*").eq("organization_id", organization_id)
        if site_id:
            q = q.eq("site_id", site_id)
        if asset_class:
            q = q.eq("asset_class", asset_class)
        return q.order("name").execute().data or []
    except Exception:
        return []


def create_maintenance_schedule(organization_id: str, asset_id: str, fields: dict) -> dict | None:
    client = get_client()
    if not client or not organization_id:
        return None
    try:
        row = {k: v for k, v in fields.items() if v is not None}
        row["organization_id"] = organization_id
        row["asset_id"] = asset_id
        res = client.table("maintenance_schedules").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


# ── KPI aggregation (Phase 7) ─────────────────────────────────────────────────

def kpi_summary(organization_id: str, include_financial: bool = False) -> dict:
    """Org-scoped management aggregates from authorized source tables. Financial
    figures (inventory valuation) only included when include_financial is set."""
    client = get_client()
    out = {"corrective_actions": {}, "inventory": {}, "compliance": _empty_compliance_kpi()}
    if not client or not organization_id:
        return out
    try:
        ca = (client.table("corrective_actions").select("status")
              .eq("organization_id", organization_id).execute().data) or []
        counts: dict = {}
        for r in ca:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        out["corrective_actions"] = {
            "total": len(ca),
            "open": counts.get("open", 0) + counts.get("in_progress", 0),
            "pending_approval": counts.get("pending_approval", 0),
            "closed": counts.get("closed", 0),
            "by_status": counts,
        }
    except Exception:
        pass
    try:
        from core.inventory import balance, is_low_stock
        items = (client.table("inventory_items").select("*")
                 .eq("organization_id", organization_id).execute().data) or []
        rows = (client.table("inventory_ledger").select("item_id,location_id,qty_delta")
                .eq("organization_id", organization_id).execute().data) or []
        low = 0
        total_value = 0.0
        for it in items:
            qty = float(balance(rows, item_id=it["id"]))
            if is_low_stock(qty, it.get("reorder_threshold")):
                low += 1
            total_value += qty * float(it.get("unit_cost") or 0)
        out["inventory"] = {"item_count": len(items), "low_stock_items": low}
        if include_financial:
            out["inventory"]["total_valuation"] = total_value
    except Exception:
        pass
    try:
        out["compliance"] = _compliance_kpi(client, organization_id)
    except Exception:
        # Degrade to zeros, never omit: the dashboard must be able to tell
        # "no certificates" from "endpoint broken", and a missing key reads as
        # the latter.
        out["compliance"] = _empty_compliance_kpi()
    return out


def _empty_compliance_kpi() -> dict:
    return {
        "certificates": 0,
        "compliant": 0,
        "non_compliant": 0,
        "incomplete": 0,
        "no_verdict": 0,
        "pending_review": 0,
        "failing_parameters": 0,
        "latest_sampled_at": None,
    }


# reviewer_status values that mean a human has finished with the certificate.
# Anything else — including a missing value — is still awaiting review.
_REVIEW_SETTLED = {"approved", "corrected"}


def _compliance_kpi(client, organization_id: str) -> dict:
    """Certificate verdict tallies for one organisation.

    Two queries regardless of how many certificates exist: one for the samples,
    one (via count_lab_results_by_status) for every parameter row behind them.

    Verdicts are counted exactly as stored. A certificate with no
    overall_status is `no_verdict`, never a pass, and INCOMPLETE is its own
    bucket — folding either into `compliant` would put a compliance claim on a
    management dashboard that no laboratory ever made.
    """
    out = _empty_compliance_kpi()
    rows = (client.table("lab_samples")
            .select("id,overall_status,reviewer_status,sampled_at")
            .eq("organization_id", organization_id).execute().data) or []
    if not rows:
        return out

    bucket = {"COMPLIANT": "compliant", "NON_COMPLIANT": "non_compliant",
              "INCOMPLETE": "incomplete"}
    latest = None
    for r in rows:
        status = (r.get("overall_status") or "").strip().upper()
        out[bucket.get(status, "no_verdict")] += 1
        if (r.get("reviewer_status") or "").strip().lower() not in _REVIEW_SETTLED:
            out["pending_review"] += 1
        sampled = r.get("sampled_at")
        if sampled and (latest is None or str(sampled) > str(latest)):
            latest = sampled

    out["certificates"] = len(rows)
    out["latest_sampled_at"] = str(latest) if latest else None
    counts = count_lab_results_by_status([r["id"] for r in rows if r.get("id")])
    out["failing_parameters"] = sum(c.get("fail", 0) for c in counts.values())
    return out


def list_inventory_locations(organization_id: str) -> list[dict]:
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        return (client.table("inventory_locations").select("*")
                .eq("organization_id", organization_id).order("name").execute().data) or []
    except Exception:
        return []


# ── Report types (migration 017) ─────────────────────────────────────────────

def list_custom_report_types(organization_id: str) -> list[dict]:
    """Organisation-defined report types. Built-ins live in core/report_types.py."""
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        return (client.table("report_types").select("*")
                .eq("organization_id", organization_id).order("name").execute().data) or []
    except Exception:
        # Table absent until 017 is applied — the built-in types still work.
        return []


def create_report_type(organization_id: str, name: str,
                       created_by: str | None = None) -> dict | None:
    """Insert a custom report type. Returns the row, or None on failure.

    No scope: migration 019 removed it. A report type records what analysis was
    performed; which limits apply is decided by the asset the certificate is about.
    """
    client = get_client()
    if not client or not organization_id:
        return None
    row = {"organization_id": organization_id, "name": name}
    if created_by:
        row["created_by"] = created_by
    res = client.table("report_types").insert(row).execute()
    return res.data[0] if res.data else None


# ── Lab samples (migration 016) ──────────────────────────────────────────────

# Columns lab_samples actually has. A parsed LabSample carries more than the
# table stores (raw text, gate findings), so the payload is filtered rather than
# splatted — an unexpected key would fail the whole insert.
_LAB_SAMPLE_COLUMNS = {
    "site_id", "asset_id", "asset_type", "laboratory", "report_no", "form_type", "report_type",
    "sampling_point", "sample_location", "sample_identification",
    "source_of_sample", "sample_description", "sampled_at", "received_at",
    "reported_at", "analysis_start", "analysis_end", "sampling_time",
    "sampled_by", "sampling_method", "sampling_apparatus", "sample_volume",
    "temperature_c", "analyst", "reviewed_by", "remarks", "source_filename",
    "source_sha256", "extraction_method", "extraction_confidence",
    "reviewer_status", "anomalies", "raw_extraction",
    # Governing standard + method disclosure (migration 018). Without these the
    # citation a verdict rests on survives only inside raw_extraction — evidence,
    # but not queryable, so nothing could report on which standard was applied.
    "standard_code", "standard_title", "standard_year", "standard_authority",
    "standard_citation", "additional_standards", "test_procedure",
    "medium_used", "detection_limit", "filtered_volume", "overall_status",
}
_LAB_RESULT_COLUMNS = {
    "parameter", "test_method", "unit", "value_raw", "value_num", "qualifier",
    "loq", "mou", "specification", "status",
}


def save_lab_sample(organization_id: str, sample: dict, results: list[dict],
                    site_id: str | None = None) -> str | None:
    """Persist one certificate and its parameter rows. Returns the sample id.

    The two inserts are not a transaction — PostgREST has no cross-request
    transaction — so a failure part-way is cleaned up by deleting the parent,
    which cascades. A sample with no results would look like a certificate that
    reported nothing, which is worse than no record at all.
    """
    client = get_client()
    if not client or not organization_id:
        return None

    row = {k: v for k, v in sample.items() if k in _LAB_SAMPLE_COLUMNS}
    row["organization_id"] = organization_id
    if site_id:
        row["site_id"] = site_id
    row.setdefault("reviewer_status", "pending")

    res = client.table("lab_samples").insert(row).execute()
    if not res.data:
        return None
    sample_id = res.data[0]["id"]

    payload = [
        {**{k: v for k, v in r.items() if k in _LAB_RESULT_COLUMNS}, "sample_id": sample_id}
        for r in results
    ]
    if payload:
        try:
            client.table("lab_results").insert(payload).execute()
        except Exception:
            client.table("lab_samples").delete().eq("id", sample_id).execute()
            raise
    return sample_id


def list_lab_samples(organization_id: str, limit: int = 50,
                     site_id: str | None = None) -> list[dict]:
    """Recent certificates for an organisation, newest sampling date first.

    `site_id` is optional and, when given, must already have been resolved
    inside the caller's organisation — this never widens the org filter.
    """
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        q = (client.table("lab_samples").select("*")
             .eq("organization_id", organization_id))
        if site_id:
            q = q.eq("site_id", site_id)
        return (q.order("sampled_at", desc=True).limit(limit).execute().data) or []
    except Exception:
        return []


def find_site_id(site_name: str, organization_id: str) -> str | None:
    """Resolve a site name to its id WITHOUT creating it.

    get_or_create_site_id() is the write path; a read filter must never bring a
    site into existence as a side effect of someone typing a name in a query
    string.
    """
    client = get_client()
    if not client or not organization_id or not site_name:
        return None
    try:
        res = (client.table("sites").select("id")
               .eq("organization_id", organization_id)
               .eq("name", site_name).execute())
        return res.data[0]["id"] if res.data else None
    except Exception:
        return None


def count_lab_results_by_status(sample_ids: list[str]) -> dict[str, dict[str, int]]:
    """Per-sample parameter counts keyed by sample_id.

    One query for the whole page of certificates, not one per certificate: the
    certificate list is the compliance report's headline, and an N+1 over
    lab_results would make it degrade with every report ever filed. Returns
    {sample_id: {"fail": n, "pass": n, "not_assessed": n, "total": n}}.
    Callers must scope `sample_ids` to their organisation first — lab_results
    carries no organization_id of its own.
    """
    client = get_client()
    if not client or not sample_ids:
        return {}
    counts: dict[str, dict[str, int]] = {
        sid: {"fail": 0, "pass": 0, "not_assessed": 0, "total": 0} for sid in sample_ids
    }
    try:
        rows = (client.table("lab_results").select("sample_id,status")
                .in_("sample_id", sample_ids).execute().data) or []
    except Exception:
        return counts
    key = {"FAIL": "fail", "PASS": "pass", "NOT_ASSESSED": "not_assessed"}
    for r in rows:
        bucket = counts.get(r.get("sample_id"))
        if bucket is None:
            continue
        bucket["total"] += 1
        k = key.get(r.get("status") or "")
        if k:
            bucket[k] += 1
    return counts


def get_asset(asset_id: str, organization_id: str) -> dict | None:
    """One asset, scoped to the organisation so an id from elsewhere cannot leak in."""
    client = get_client()
    if not client or not asset_id or not organization_id:
        return None
    try:
        res = (client.table("assets").select("*")
               .eq("id", asset_id).eq("organization_id", organization_id).execute())
        return res.data[0] if res.data else None
    except Exception:
        return None



# ── Asset types (migration 020) ──────────────────────────────────────────────

def list_asset_types(organization_id: str) -> list[dict]:
    """Organisation-defined asset types. Built-ins live in core/assets.py."""
    client = get_client()
    if not client or not organization_id:
        return []
    try:
        return (client.table("asset_types").select("*")
                .eq("organization_id", organization_id).order("label").execute().data) or []
    except Exception:
        # Table absent until 020 is applied — built-in types still work.
        return []


def create_asset_type(organization_id: str, key: str, label: str, asset_class: str,
                      scope: str | None = None, created_by: str | None = None) -> dict | None:
    """Add an organisation-defined asset type. Returns the row, or None."""
    client = get_client()
    if not client or not organization_id:
        return None
    row = {"organization_id": organization_id, "key": key, "label": label,
           "asset_class": asset_class, "scope": scope}
    if created_by:
        row["created_by"] = created_by
    res = client.table("asset_types").insert(row).execute()
    return res.data[0] if res.data else None


def delete_asset_type(organization_id: str, key: str) -> bool:
    """Remove a custom type. Assets already using it keep working — they store
    asset_type/asset_class/scope by value, not by reference."""
    client = get_client()
    if not client or not organization_id:
        return False
    try:
        client.table("asset_types").delete() \
            .eq("organization_id", organization_id).eq("key", key).execute()
        return True
    except Exception:
        return False
