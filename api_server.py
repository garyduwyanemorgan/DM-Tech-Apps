"""Lagoon DECCA — FastAPI HTTP server.

Exposes the same compliance + alert logic as the MCP server but over
HTTP, so Sakhile's Vonage/n8n voice pipeline can call it with a simple
HTTP Request node.

Run locally:
    cd dashboard
    SUPABASE_URL=... SUPABASE_KEY=... python -m uvicorn api_server:app --reload --port 8000

Production (background):
    uvicorn api_server:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health                   — liveness check
    GET  /sites                    — list configured sites
    POST /assess                   — check readings, no save
    POST /log                      — save reading + return assessment
    GET  /status/{site}            — all readings for a site this year
    GET  /tools                    — OpenAPI-style tool schemas (for Claude tool use in n8n)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Optional

# Make core/, db/, data/ importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Security, Header, Depends, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from core.alert_engine import evaluate_alert_level
from core.calculations import check_all_compliance, compliance_summary
from core.constants import ALERT_LABELS, MONTH_NAMES, TREATMENT_ACTIONS, AlertLevel
from core.models import WaterReading

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lagoon DECCA API",
    description="Water quality compliance + alert engine for Dubai lagoon field teams.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten to n8n host in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Optional API key auth (set API_KEY env var to enable) ────────────────────

_API_KEY = os.environ.get("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _check_key(key: str | None = Security(api_key_header)):
    if _API_KEY and key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


# ── JWT Auth & Roles Middleware (SaaS Phase 2) ───────────────────────────────

security_jwt = HTTPBearer(auto_error=False)

_clerk_jwks_cache: dict | None = None


def _clerk_publishable_key() -> str:
    """Resolve the Clerk publishable key from secrets.toml or the env var.

    On Render/serverless there is no secrets.toml, so CLERK_PUBLISHABLE_KEY must
    be set as an environment variable; locally the .streamlit/secrets.toml value
    takes precedence.
    """
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # Python < 3.11 fallback
    try:
        with open(os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml"), "rb") as f:
            secrets = tomllib.load(f)
        pk = secrets.get("clerk", {}).get("publishable_key", "")
        if pk:
            return pk
    except Exception:
        pass
    return os.environ.get("CLERK_PUBLISHABLE_KEY", "")


def _clerk_jwks_url() -> str:
    """Derive the per-instance JWKS URL from the Clerk publishable key."""
    import base64
    try:
        pk = _clerk_publishable_key()
        if pk.startswith("pk_"):
            b64 = pk.split("_", 2)[2]
            b64 += "=" * (4 - len(b64) % 4)
            domain = base64.b64decode(b64).decode().rstrip("$")
            return f"https://{domain}/.well-known/jwks.json"
    except Exception:
        pass
    return "https://api.clerk.com/v1/jwks"


def get_user_from_token(token: str | None) -> dict | None:
    """Validate a Clerk JWT via the instance JWKS, returning the user's Clerk ID and email."""
    if not token:
        return None
    try:
        import jwt as pyjwt
        from jwt.algorithms import RSAAlgorithm
        import json as _json
        import httpx as _httpx

        global _clerk_jwks_cache
        if not _clerk_jwks_cache or not _clerk_jwks_cache.get("keys"):
            url = _clerk_jwks_url()
            r = _httpx.get(url, timeout=5)
            _clerk_jwks_cache = r.json()

        header = pyjwt.get_unverified_header(token)
        kid = header.get("kid")
        key_data = next(
            (k for k in _clerk_jwks_cache.get("keys", []) if k["kid"] == kid), None
        )
        if not key_data:
            # kid not in cache — JWKS may have rotated; refetch once
            url = _clerk_jwks_url()
            _clerk_jwks_cache = _httpx.get(url, timeout=5).json()
            key_data = next(
                (k for k in _clerk_jwks_cache.get("keys", []) if k["kid"] == kid), None
            )
            if not key_data:
                print(f"[clerk-auth] no JWKS key for kid={kid}", file=sys.stderr)
                return None
        public_key = RSAAlgorithm.from_jwk(_json.dumps(key_data))
        # leeway tolerates clock skew on Clerk's short-lived tokens (exp/nbf/iat);
        # Clerk's own backend SDKs allow ~60s. Skip aud/iss checks (not set by default).
        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            leeway=60,
            options={"verify_aud": False},
        )
        return {
            "id": payload["sub"],
            "email": payload.get("email", ""),
        }
    except Exception as exc:
        print(f"[clerk-auth] token verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return None


def get_user_profile(user_id: str, email: str = "", token: str | None = None) -> dict | None:
    """Fetch user profile by Clerk ID; falls back to email to link invited profiles."""
    from db.client import get_client
    client = get_client()
    if not client:
        return None
    try:
        # Primary: look up by Clerk user ID
        res = client.table("user_profiles").select("*").eq("clerk_id", user_id).execute()
        if res.data:
            return res.data[0]
        # Email fallback: link a pending invited profile on first sign-in
        if email:
            res = (
                client.table("user_profiles")
                .select("*")
                .eq("email", email)
                .is_("clerk_id", "null")
                .execute()
            )
            if res.data:
                profile = res.data[0]
                client.table("user_profiles").update({"clerk_id": user_id}).eq(
                    "id", profile["id"]
                ).execute()
                profile["clerk_id"] = user_id  # reflect the link in the returned dict
                return profile
    except Exception:
        pass
    return None


def _personal_org_name(email: str, user_id: str) -> str:
    """Deterministic personal-organization name for an uninvited user."""
    return f"{email or user_id}'s Organization"


def _create_super_admin_profile(user_id: str, email: str) -> str | None:
    """Auto-provision a new uninvited user on first sign-in: create a personal
    organization (default Starter plan, 1 site) and a super_admin profile linked
    to it. Returns the new organization_id (or None if the DB is unavailable)."""
    from db.client import get_client
    from db.queries import create_organization
    import uuid as _uuid
    client = get_client()
    if not client:
        return None
    org_id = create_organization(_personal_org_name(email, user_id))
    try:
        client.table("user_profiles").insert({
            "id": str(_uuid.uuid4()),
            "clerk_id": user_id,
            "email": email,
            "role": "super_admin",
            "organization_id": org_id,
        }).execute()
    except Exception:
        pass
    return org_id


def _ensure_org_for_profile(profile: dict, email: str, user_id: str) -> str | None:
    """Ensure an existing profile has an organization. Uninvited users (and any
    user left without a role/org) get a personal organization auto-created and
    linked on sign-in. Returns the profile's organization_id."""
    org_id = profile.get("organization_id")
    if org_id:
        return org_id
    from db.client import get_client
    from db.queries import create_organization
    client = get_client()
    if not client:
        return None
    org_id = create_organization(_personal_org_name(email, user_id))
    if not org_id:
        return None
    updates = {"organization_id": org_id}
    if not profile.get("role"):
        updates["role"] = "super_admin"
    try:
        client.table("user_profiles").update(updates).eq("id", profile["id"]).execute()
    except Exception:
        pass
    return org_id


def get_current_user_profile(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_jwt),
    x_organization_id: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
) -> dict:
    """
    Validate Bearer token or fallback to API Key / headers.
    Returns dict with {"user_id", "organization_id", "role", "token"}.
    New uninvited users are auto-created as super_admin; invited users keep the role set by host.
    """
    token = credentials.credentials if credentials else None
    user = get_user_from_token(token)
    if user:
        email = x_user_email or user.get("email") or ""
        profile = get_user_profile(user["id"], email=email, token=token)
        if profile:
            # Auto-provision a personal org for users left without one
            # (uninvited / role-less); invited users already carry an org.
            org_id = _ensure_org_for_profile(profile, email, user["id"])
            return {
                "user_id": user["id"],
                "email": email,
                "organization_id": org_id,
                "role": profile.get("role") or "super_admin",
                "token": token,
            }
        # No profile and no matching invite — new uninvited user: create a
        # super_admin profile + personal organization.
        org_id = _create_super_admin_profile(user["id"], email)
        return {
            "user_id": user["id"],
            "email": email,
            "organization_id": org_id,
            "role": "super_admin",
            "token": token,
        }

    # Fallback to organization ID from header (for backwards compatibility / API keys)
    return {
        "user_id": None,
        "organization_id": x_organization_id,
        "role": "operator",
        "token": None,
    }


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReadingFields(BaseModel):
    ph:               float = Field(..., description="pH units (DECCA: 6.0–9.0)")
    do:               float = Field(..., description="Dissolved oxygen mg/L (DECCA: >4.0)")
    tss:              float = Field(..., description="Total suspended solids mg/L (DECCA: <50)")
    turbidity:        float = Field(..., description="Turbidity NTU (DECCA: <75)")
    cod:              float = Field(..., description="Chemical oxygen demand mg/L (DECCA: <50)")
    ammonia:          float = Field(..., description="Ammonia as N mg/L (DECCA: <5.0)")
    phosphate:        float = Field(..., description="Total phosphate mg/L (DECCA: <5.0)")
    oil_grease:       float = Field(..., description="Oils & grease mg/L (DECCA: <10)")
    ecoli:            float = Field(..., description="E. coli CFU/100mL (DECCA: <200)")
    total_coliforms:  float = Field(..., description="Total coliforms CFU/100mL (DECCA: <1000)")
    chla:             float = Field(..., description="Chlorophyll-a µg/L (bloom watch >10)")
    phycocyanin:      float = Field(..., description="Phycocyanin µg/L (cyano watch >50)")
    salinity:         float = Field(..., description="Salinity PSU (typical 40–60)")
    water_temp:       float = Field(..., description="Water temperature °C (typical 22–33)")


class AssessRequest(ReadingFields):
    pass


class LogRequest(ReadingFields):
    site:      str           = Field(..., description="Site name, e.g. 'Emaar'")
    year:      int           = Field(..., description="Reading year, e.g. 2026")
    month:     int           = Field(..., ge=1, le=12, description="Reading month 1–12")
    overwrite: bool          = Field(False, description="Replace existing reading for same site/month")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_reading(f: ReadingFields, when: datetime | None = None) -> WaterReading:
    return WaterReading(
        timestamp=when or datetime.now(),
        ph=f.ph, do=f.do, tss=f.tss, turbidity=f.turbidity,
        cod=f.cod, ammonia=f.ammonia, phosphate=f.phosphate,
        oil_grease=f.oil_grease, ecoli=f.ecoli,
        total_coliforms=f.total_coliforms, chla=f.chla,
        phycocyanin=f.phycocyanin, salinity=f.salinity, water_temp=f.water_temp,
    )


def _assess(reading: WaterReading) -> dict:
    results = check_all_compliance(reading)
    summary = compliance_summary(results)
    alert   = evaluate_alert_level(reading)
    level   = AlertLevel(alert.level)
    tx      = TREATMENT_ACTIONS[level]
    return {
        "compliance": {
            "overall_status":  summary["overall_status"],
            "compliance_pct":  summary["compliance_pct"],
            "failing_params":  summary["failing_params"],
            "min_margin_pct":  summary["min_margin"],
            "per_parameter": [
                {
                    "parameter": r.parameter_name,
                    "value":     r.value,
                    "unit":      r.unit,
                    "limit":     r.limit_display,
                    "compliant": r.compliant,
                    "margin_pct":r.margin_pct,
                    "risk":      r.risk_level,
                }
                for r in results
            ],
        },
        "alert": {
            "level":                int(level),
            "label":                ALERT_LABELS[level],
            "bloom_probability_pct":alert.bloom_probability,
            "dominant_species":     alert.dominant_species,
            "drivers":              alert.top_drivers,
        },
        "treatment_response": {
            "enzyme":     tx.enzyme,
            "aeration":   tx.aeration,
            "ultrasound": tx.ultrasound,
            "monitoring": tx.monitoring,
            "do_not":     tx.do_not,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Liveness check. Returns ok when the server is running."""
    return {"status": "ok", "service": "lagoon-decca-api"}


class CreateSiteRequest(BaseModel):
    name:               str   = Field(..., min_length=1, max_length=80, description="Unique site name")
    volume_m3:          float = Field(0.0,  ge=0, description="Lagoon volume in cubic metres")
    salinity_baseline:  float = Field(45.0, ge=0, description="Baseline salinity PSU")


@app.get("/sites", tags=["Sites"])
def list_sites(profile: dict = Depends(get_current_user_profile)):
    """Return site names with reading counts for the authenticated tenant (2 queries)."""
    org_id = profile.get("organization_id")
    if not org_id:
        return {"sites": []}
    try:
        from db.client import get_client
        from collections import Counter
        client = get_client()
        if not client:
            return {"sites": []}
        # Query 1: all sites for this org
        sites_res = client.table("sites").select("id, name").eq("organization_id", org_id).execute()
        if not sites_res.data:
            return {"sites": []}
        site_ids = [s["id"] for s in sites_res.data]
        # Query 2: reading counts for all sites at once
        readings_res = client.table("readings").select("site_id").in_("site_id", site_ids).execute()
        counts = Counter(r["site_id"] for r in (readings_res.data or []))
        sites = [{"name": s["name"], "reading_count": counts.get(s["id"], 0)} for s in sites_res.data]
    except Exception:
        sites = []
    return {"sites": sites}


@app.post("/sites", tags=["Sites"], status_code=201)
def create_site_endpoint(body: CreateSiteRequest, profile: dict = Depends(get_current_user_profile)):
    """Create a new site for the tenant. Requires admin or super_admin role. Enforces plan site limit."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Only admins can create sites.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")

    # ── Billing: enforce site limit ──────────────────────────────────────────
    from billing import get_org_billing, count_sites, PLANS
    billing = get_org_billing(org_id)
    site_limit = billing.get("site_limit", 1)
    current_count = count_sites(org_id)
    if current_count >= site_limit:
        plan_name = billing.get("plan_name", "starter")
        plan = PLANS.get(plan_name, PLANS["starter"])
        raise HTTPException(
            status_code=402,
            detail=(
                f"Site limit reached: your {plan['name']} plan allows {site_limit} "
                f"site{'s' if site_limit != 1 else ''}. Upgrade your plan to add more sites."
            ),
        )

    try:
        from db.queries import create_site, get_site_names
        existing = get_site_names(organization_id=profile["organization_id"], token=profile["token"])
        if body.name in existing:
            raise HTTPException(status_code=409, detail=f"Site '{body.name}' already exists.")
        site_id = create_site(
            organization_id=profile["organization_id"],
            name=body.name,
            volume_m3=body.volume_m3,
            salinity_baseline=body.salinity_baseline,
            token=profile["token"],
        )
        if not site_id:
            raise HTTPException(status_code=500, detail="Failed to create site.")
        return {"site_id": site_id, "name": body.name, "message": f"Site '{body.name}' created."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/sites/{site_name}", tags=["Sites"])
def delete_site_endpoint(site_name: str, profile: dict = Depends(get_current_user_profile)):
    """Delete a site and ALL associated readings/predictions. Requires admin or super_admin."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Only admins can delete sites.")
    try:
        from db.queries import delete_site
        ok, msg, count = delete_site(
            site_name=site_name,
            organization_id=profile.get("organization_id"),
            token=profile["token"],
        )
        if not ok:
            raise HTTPException(status_code=404, detail=msg)
        return {"deleted": True, "message": msg, "readings_deleted": count}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/profile", tags=["Auth"])
def get_profile(profile: dict = Depends(get_current_user_profile)):
    """Return current user's role and org. Returns pending state for users not yet assigned to an org."""
    return {
        "user_id": profile.get("user_id"),
        "organization_id": profile.get("organization_id"),
        "role": profile.get("role", "super_admin"),
        "pending": profile.get("organization_id") is None and profile.get("user_id") is not None,
    }


# ── User management ───────────────────────────────────────────────────────────

class UpdateRoleRequest(BaseModel):
    role: str

class InviteRequest(BaseModel):
    email: str
    role: str = "operator"


@app.get("/users", tags=["Users"])
def list_users(profile: dict = Depends(get_current_user_profile)):
    """List all users in the organisation. Requires admin or super_admin."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    org_id = profile.get("organization_id")
    if not org_id:
        return {"users": []}
    from db.client import get_client as _gc
    client = _gc()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available.")
    try:
        profiles_res = client.table("user_profiles").select("id, role").eq("organization_id", org_id).execute()
        if not profiles_res.data:
            return {"users": []}
        profile_map = {p["id"]: p["role"] for p in profiles_res.data}
        auth_users = client.auth.admin.list_users()
        users = []
        for u in auth_users:
            if u.id not in profile_map:
                continue
            users.append({
                "id": u.id,
                "email": getattr(u, "email", None) or "",
                "role": profile_map[u.id],
                "created_at": str(getattr(u, "created_at", "")),
                "last_sign_in": str(getattr(u, "last_sign_in_at", "") or ""),
                "provider": (getattr(u, "app_metadata", {}) or {}).get("provider", "email"),
            })
        return {"users": users}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.patch("/users/{user_id}", tags=["Users"])
def update_user_role(user_id: str, body: UpdateRoleRequest, profile: dict = Depends(get_current_user_profile)):
    """Change a user's role. Admins can set operator/admin; only super_admin can grant super_admin."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    if body.role not in ("operator", "admin", "super_admin"):
        raise HTTPException(status_code=422, detail="Role must be operator, admin, or super_admin.")
    if body.role == "super_admin" and profile.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can grant super_admin role.")
    if user_id == profile.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot change your own role.")
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    client = _gc()
    res = client.table("user_profiles").update({"role": body.role}).eq("id", user_id).eq("organization_id", org_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    return {"updated": True, "user_id": user_id, "role": body.role}


@app.delete("/users/{user_id}", tags=["Users"])
def remove_user(user_id: str, profile: dict = Depends(get_current_user_profile)):
    """Remove a user from the organisation (deletes their profile). Requires admin or super_admin."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    if user_id == profile.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot remove yourself.")
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    client = _gc()
    # Ensure target is in same org and not higher-ranked
    target = client.table("user_profiles").select("role").eq("id", user_id).eq("organization_id", org_id).execute()
    if not target.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    target_role = target.data[0]["role"]
    if target_role == "super_admin" and profile.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can remove a super_admin.")
    client.table("user_profiles").delete().eq("id", user_id).eq("organization_id", org_id).execute()
    return {"removed": True, "user_id": user_id}


@app.post("/users/invite", tags=["Users"], status_code=201)
def invite_user(body: InviteRequest, profile: dict = Depends(get_current_user_profile)):
    """
    Pre-create a pending user profile for an invited email address.
    The clerk_id is null until the user signs up via Clerk and their first sign-in
    triggers an email-based profile link in get_user_profile().
    TODO: send invite email via Clerk Invitations API or a transactional email service.
    """
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    if body.role not in ("operator", "admin", "super_admin"):
        raise HTTPException(status_code=422, detail="Invalid role.")
    if body.role == "super_admin" and profile.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can invite as super_admin.")
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    import uuid as _uuid
    client = _gc()
    try:
        # Check for an existing profile with this email
        existing = client.table("user_profiles").select("id").eq("email", body.email).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail=f"{body.email} is already invited or registered.")
        client.table("user_profiles").insert({
            "id": str(_uuid.uuid4()),
            "organization_id": org_id,
            "role": body.role,
            "email": body.email,
            # clerk_id left null — linked on first Clerk sign-in
        }).execute()
        return {"invited": True, "email": body.email, "role": body.role}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Billing ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    success_url: str
    cancel_url: str

class PortalRequest(BaseModel):
    return_url: str


@app.get("/billing/status", tags=["Billing"])
def billing_status(profile: dict = Depends(get_current_user_profile)):
    """Return current plan, site usage, and whether Stripe is configured."""
    from billing import get_org_billing, count_sites, PLANS, is_configured
    org_id = profile.get("organization_id")
    if not org_id:
        # No org yet (e.g. fresh super_admin). Return a complete, well-formed shape so the
        # billing panel renders the plan catalog instead of crashing on missing fields.
        return {
            "plan":              "none",
            "plan_name":         "No Plan",
            "plan_description":  "Create or join an organization to manage a subscription.",
            "site_limit":        0,
            "sites_used":        0,
            "can_add_site":      False,
            "has_subscription":  False,
            "stripe_configured": is_configured(),
            "available_plans":   PLANS,
        }
    billing = get_org_billing(org_id)
    plan_key = billing.get("plan_name", "starter")
    site_limit = billing.get("site_limit", 1)
    sites_used = count_sites(org_id)
    plan_info = PLANS.get(plan_key, PLANS["starter"])
    return {
        "plan":              plan_key,
        "plan_name":         plan_info["name"],
        "plan_description":  plan_info["description"],
        "site_limit":        site_limit,
        "sites_used":        sites_used,
        "can_add_site":      sites_used < site_limit,
        "has_subscription":  bool(billing.get("stripe_subscription_id")),
        "stripe_configured": is_configured(),
        "available_plans":   PLANS,
    }


@app.post("/billing/checkout", tags=["Billing"])
def billing_checkout(body: CheckoutRequest, profile: dict = Depends(get_current_user_profile)):
    """Create a Stripe Checkout session and return the redirect URL."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    from billing import create_checkout_session, is_configured, PLANS
    if not is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured. Add stripe.secret_key to secrets.toml.")
    if body.plan not in PLANS:
        raise HTTPException(status_code=422, detail=f"Unknown plan '{body.plan}'. Choose: {', '.join(PLANS.keys())}")
    org_id = profile.get("organization_id", "")
    # Use a placeholder email if we only have user_id
    user_email = profile.get("email", f"{profile.get('user_id', 'user')}@lagoon.app")
    url = create_checkout_session(
        org_id=org_id,
        plan_key=body.plan,
        user_email=user_email,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )
    if not url:
        raise HTTPException(status_code=500, detail=f"No Stripe price ID configured for plan '{body.plan}'.")
    return {"checkout_url": url}


@app.post("/billing/portal", tags=["Billing"])
def billing_portal(body: PortalRequest, profile: dict = Depends(get_current_user_profile)):
    """Create a Stripe Customer Portal session for plan/payment management."""
    if profile.get("role") not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    from billing import create_portal_session, is_configured
    if not is_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured.")
    org_id = profile.get("organization_id", "")
    url = create_portal_session(org_id=org_id, return_url=body.return_url)
    if not url:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer record found. Complete a checkout first.",
        )
    return {"portal_url": url}


@app.post("/billing/webhook", tags=["Billing"], include_in_schema=False)
async def billing_webhook(request: Request):
    """Stripe webhook — updates org plan and site_limit on subscription events."""
    from billing import handle_webhook, is_configured
    if not is_configured():
        raise HTTPException(status_code=503, detail="Stripe not configured.")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = handle_webhook(payload, sig)
    if not result.get("handled") and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"received": True, "event_type": result.get("event_type")}


@app.post("/assess", tags=["Compliance"])
def assess(body: AssessRequest, _=Security(_check_key)):
    """Check a set of readings against DECCA limits and the alert engine.
    Does NOT save to the database — use this to validate before logging,
    or when a field team just wants a quick compliance check.
    """
    reading = _build_reading(body)
    return _assess(reading)


@app.post("/log", tags=["Compliance"])
def log_reading(body: LogRequest, _=Security(_check_key), profile: dict = Depends(get_current_user_profile)):
    """Save a monthly reading for a site, then return the full DECCA
    compliance assessment, alert level, and treatment response.
    Enforces role validation and tenant data isolation.
    """
    if profile.get("role") not in ('admin', 'operator', 'super_admin'):
        raise HTTPException(status_code=403, detail="User role does not have permission to log water readings.")

    if not (1 <= body.month <= 12):
        raise HTTPException(status_code=422, detail="month must be 1–12")

    reading = _build_reading(body, when=datetime(body.year, body.month, 15))
    assessment = _assess(reading)

    fields = {
        "ph": body.ph, "do_mgl": body.do, "tss_mgl": body.tss,
        "turbidity_ntu": body.turbidity, "cod_mgl": body.cod,
        "ammonia_mgl": body.ammonia, "phosphate_mgl": body.phosphate,
        "oil_grease_mgl": body.oil_grease, "ecoli_cfu": body.ecoli,
        "total_coliforms_cfu": body.total_coliforms, "chla_ugl": body.chla,
        "phycocyanin_ugl": body.phycocyanin, "salinity_psu": body.salinity,
        "water_temp_c": body.water_temp,
    }

    try:
        from db.queries import insert_reading
        ok, msg = insert_reading(body.site, body.year, body.month, fields, upsert=body.overwrite,
                                 organization_id=profile["organization_id"], token=profile["token"])
    except Exception as exc:
        ok, msg = False, str(exc)

    return {
        "saved":      ok,
        "message":    msg,
        "site":       body.site,
        "period":     f"{MONTH_NAMES[body.month - 1]} {body.year}",
        "assessment": assessment,
    }


@app.get("/status/{site}", tags=["Compliance"])
def site_status(site: str, year: int = 2026, _=Security(_check_key), profile: dict = Depends(get_current_user_profile)):
    """Return all stored readings for a site in a given year, each with
    its compliance status and alert level. Scopes lookup to the user's organization.
    """
    try:
        from db.queries import get_readings_for_site
        readings = get_readings_for_site(site, year=year, organization_id=profile["organization_id"], token=profile["token"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not readings:
        return {"site": site, "year": year, "readings": [],
                "note": "No readings stored yet."}

    months = []
    for r in readings:
        a = _assess(r)
        months.append({
            "month":           MONTH_NAMES[r.timestamp.month - 1],
            "compliance":      a["compliance"]["overall_status"],
            "compliance_pct":  a["compliance"]["compliance_pct"],
            "alert_level":     a["alert"]["level"],
            "alert_label":     a["alert"]["label"],
            "failing_params":  a["compliance"]["failing_params"],
        })

    return {"site": site, "year": year, "readings": months}


@app.get("/tools", tags=["System"])
def tool_schemas():
    """Return OpenAPI-style tool definitions for use with Claude API
    tool use in n8n. Pass these as the `tools` array in the Anthropic
    Messages API call so Claude knows what our endpoints accept.
    """
    return {
        "tools": [
            {
                "name": "assess_reading",
                "description": "Check water quality values against DECCA limits. No save.",
                "endpoint": "POST /assess",
                "input_schema": AssessRequest.model_json_schema(),
            },
            {
                "name": "log_reading",
                "description": "Save a monthly reading and return DECCA compliance + alert level.",
                "endpoint": "POST /log",
                "input_schema": LogRequest.model_json_schema(),
            },
            {
                "name": "get_site_status",
                "description": "Get all readings for a site this year with compliance status.",
                "endpoint": "GET /status/{site}",
            },
            {
                "name": "diagnose_lagoon",
                "description": "Run the full scientific chain: nutrient source, internal loading, residence time, bloom forecast + interventions.",
                "endpoint": "POST /science/diagnose",
            },
            {
                "name": "simulate_intervention",
                "description": "Digital twin: simulate a management intervention and predict bloom reduction.",
                "endpoint": "POST /science/simulate",
            },
        ]
    }


# ════════════════════════════════════════════════════════════════════════════
# SCIENCE ENGINES (v2) — additive endpoints. v1 routes above are unchanged.
# ════════════════════════════════════════════════════════════════════════════

class DiagnoseRequest(BaseModel):
    # Core chemistry (from a WaterReading)
    temperature:      float = Field(..., description="Water temperature °C")
    phosphate:        float = Field(..., description="Phosphate mg/L")
    ammonia:          float = Field(..., description="Ammonia as N mg/L")
    dissolved_oxygen: float = Field(..., description="DO mg/L")
    salinity:         float = Field(..., description="Salinity PSU")
    nitrate:          float = Field(0.0, description="Nitrate as N mg/L (optional)")
    # Hydraulics (optional — enables residence time + interventions)
    volume_m3:            float = Field(0.0, description="Lagoon volume m³")
    inflow_m3_day:        float = Field(0.0, description="Inflow m³/day")
    outflow_m3_day:       float = Field(0.0, description="Outflow m³/day")
    recirculation_m3_day: float = Field(0.0, description="Recirculation m³/day")
    # Sediment
    orp:            Optional[float] = Field(None, description="Redox potential mV (optional)")
    sediment_state: str = Field("normal", description="mineral / normal / organic / post_bloom")
    # Context flags
    recent_rainfall:  bool  = Field(False, description="Recent rainfall")
    dust_event:       bool  = Field(False, description="Recent dust/sandstorm")
    tse_inflow_high:  bool  = Field(False, description="Measured high TSE inflow")
    salinity_baseline:float = Field(45.0, description="Site baseline salinity PSU")
    historical_bloom_count: int = Field(0, description="Prior blooms at the site")
    include_interventions:  bool  = Field(True, description="Rank digital-twin interventions")
    intervention_magnitude: float = Field(0.5, description="Intervention strength 0–1")


class SimulateRequest(DiagnoseRequest):
    intervention: str = Field(..., description="reduce_phosphate / increase_circulation / remove_sludge / reduce_residence_time")


@app.post("/science/diagnose", tags=["Science"])
def science_diagnose(body: DiagnoseRequest, _=Security(_check_key)):
    """Run the full scientific chain for a reading and return an explainable
    diagnosis: nutrient source attribution, Fe-P internal loading, residence
    time, bloom forecast, and (optionally) a ranked list of interventions.

    Answers the operator question 'why is my lagoon turning green, and what
    should I do?'.
    """
    from science.diagnose import diagnose
    return diagnose(**body.model_dump())


@app.post("/science/simulate", tags=["Science"])
def science_simulate(body: SimulateRequest, _=Security(_check_key)):
    """Digital twin — simulate a single management intervention against the
    given state and predict the bloom-probability change and timeline.
    """
    from science.digital_twin import LagoonState, simulate
    from dataclasses import asdict
    data = body.model_dump()
    intervention = data.pop("intervention")
    magnitude = data.get("intervention_magnitude", 0.5)
    state = LagoonState(
        temperature=data["temperature"], phosphate=data["phosphate"],
        ammonia=data["ammonia"], dissolved_oxygen=data["dissolved_oxygen"],
        salinity=data["salinity"], volume_m3=data["volume_m3"],
        inflow_m3_day=data["inflow_m3_day"], outflow_m3_day=data["outflow_m3_day"],
        recirculation_m3_day=data["recirculation_m3_day"], orp=data["orp"],
        sediment_state=data["sediment_state"],
        historical_bloom_count=data["historical_bloom_count"],
    )
    try:
        return asdict(simulate(state, intervention, magnitude))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/extract", tags=["Upload"])
async def extract_lab_report_endpoint(
    file: UploadFile = File(...),
    profile: dict = Depends(get_current_user_profile),
):
    """Extract water-quality readings from a lab-report photo or PDF using Claude vision.
    Returns the 14 DECCA parameters as JSON. Human review is required before saving.
    """
    from extract import extract_lab_report, is_configured
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI extraction requires ANTHROPIC_API_KEY — set the environment variable and restart.",
        )
    content = await file.read()
    media_type = file.content_type or "image/jpeg"
    try:
        # Blocking SDK call — run off the event loop so one extraction
        # doesn't freeze every other request on the server.
        from fastapi.concurrency import run_in_threadpool
        result = await run_in_threadpool(extract_lab_report, content, media_type)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/report/{site}", tags=["Reporting"])
def download_decca_report(
    site: str,
    year: int = 2026,
    draft: bool = True,
    profile: dict = Depends(get_current_user_profile),
):
    """Generate a DECCA compliance PDF for the given site and year.
    Pass ?draft=false for a clean (watermark-free) official report.
    Returns application/pdf as an attachment download.
    """
    try:
        from db.queries import get_readings_for_site
        readings = get_readings_for_site(
            site, year=year,
            organization_id=profile["organization_id"],
            token=profile["token"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")

    if not readings:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for site '{site}' in {year}. Log at least one reading first.",
        )

    try:
        from reporting import build_decca_report
        pdf_bytes = build_decca_report(site, year, readings, draft=draft)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {exc}")

    suffix = "_DRAFT" if draft else ""
    filename = f"DECCA_{site}_{year}{suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/science/interventions", tags=["Science"])
def science_interventions():
    """List the digital-twin interventions the simulator supports."""
    from science.config import DIGITAL_TWIN_INTERVENTIONS
    return {
        "interventions": [
            {"key": iv.key, "label": iv.label,
             "time_to_effect_days": iv.time_to_effect_days,
             "description": iv.description}
            for iv in DIGITAL_TWIN_INTERVENTIONS.values()
        ]
    }


# ── Serve React Frontend directly from the FastAPI backend ──
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

api_app = app  # Keep original app with all its registered routes under the name api_app

app = FastAPI(
    title="Dubai Lagoon Management Plan",
    description="Portal serving the React frontend and backing FastAPI endpoints.",
)

# Enable CORS on the outer app to allow cross-origin API calls if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the FastAPI endpoints under the /api prefix
app.mount("/api", api_app)

# Serve the static build assets under /assets prefix
# We resolve the absolute path relative to this file
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
ASSETS_DIR = os.path.join(FRONTEND_DIR, "assets")

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

@app.get("/{catchall:path}")
def serve_react_app(catchall: str):
    # Prevent accessing files outside of FRONTEND_DIR for security
    # Clean the path to avoid directory traversal
    safe_path = os.path.normpath(catchall).lstrip(os.path.sep)
    if safe_path.startswith("..") or safe_path.startswith("/") or safe_path.startswith("\\"):
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    # Check if the requested file exists in frontend/dist (like favicon.svg, icons.svg)
    file_path = os.path.join(FRONTEND_DIR, safe_path)
    if safe_path and os.path.isfile(file_path):
        return FileResponse(file_path)

    # Otherwise return index.html for React router
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)

    return {"message": "React frontend is not built. Please run 'npm run build' inside frontend directory."}

