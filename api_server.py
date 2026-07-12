"""Lagoon Compliance — FastAPI HTTP server.

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
    GET  /version                  — deployed version + commit SHA
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
from core.audit import emit as audit_emit, emit_denial as audit_denial
from core.authz import has_permission
from core.scope import ALL_SITES, resolve_site_scope
from core.calculations import check_all_compliance, compliance_summary
from core.constants import ALERT_LABELS, MONTH_NAMES, TREATMENT_ACTIONS, AlertLevel
from core.models import WaterReading
from core.version import get_version, get_version_info

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Lagoon Compliance API",
    description="Water quality compliance + alert engine for Dubai lagoon field teams.",
    version=get_version(),
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


def _clerk_dev_publishable_key() -> str:
    """The pk_test_ key for the Clerk dev instance, if one is configured.

    Only ever set in .streamlit/secrets.toml or CLERK_DEV_PUBLISHABLE_KEY, neither
    of which exists on Render — so a value here means we are running locally and
    should authenticate against the dev instance. A live publishable key is bound
    to its registered domain and Clerk rejects it on localhost.
    """
    pk = _read_secrets_toml().get("clerk", {}).get("dev_publishable_key", "")
    return pk or os.environ.get("CLERK_DEV_PUBLISHABLE_KEY", "")


def _clerk_publishable_key() -> str:
    """Resolve the Clerk publishable key from secrets.toml or the env var.

    On Render/serverless there is no secrets.toml, so CLERK_PUBLISHABLE_KEY must
    be set as an environment variable; locally the .streamlit/secrets.toml value
    takes precedence. A configured dev key wins over both.

    This key also selects which instance's JWKS tokens are verified against
    (_clerk_jwks_url), so it must name the same instance the frontend signed the
    user in with — otherwise every authenticated request 401s.
    """
    dev_pk = _clerk_dev_publishable_key()
    if dev_pk:
        return dev_pk
    pk = _read_secrets_toml().get("clerk", {}).get("publishable_key", "")
    if pk:
        return pk
    return os.environ.get("CLERK_PUBLISHABLE_KEY", "")


def _read_secrets_toml() -> dict:
    """Load .streamlit/secrets.toml if present (local dev); {} on Render/serverless."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # Python < 3.11 fallback
    try:
        with open(os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml"), "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _clerk_secret_key() -> str:
    """Clerk Backend API secret key from secrets.toml or CLERK_SECRET_KEY env.

    Mirrors _clerk_publishable_key: a configured dev secret key wins, so Backend
    API writes land on the same instance we verify tokens against.
    """
    clerk = _read_secrets_toml().get("clerk", {})
    dev_sk = clerk.get("dev_secret_key", "") or os.environ.get("CLERK_DEV_SECRET_KEY", "")
    if dev_sk and _clerk_dev_publishable_key():
        return dev_sk
    sk = clerk.get("secret_key", "")
    return sk or os.environ.get("CLERK_SECRET_KEY", "")


def _clerk_key_instance(key: str) -> str:
    """'test', 'live', or '' — which Clerk instance a pk_/sk_ key belongs to."""
    for instance in ("test", "live"):
        if key.startswith(f"pk_{instance}_") or key.startswith(f"sk_{instance}_"):
            return instance
    return ""


def _admin_notify_email() -> str:
    """The single gatekeeper email address. New-user access requests are sent here,
    and only this address is allowed to bootstrap itself as super_admin."""
    email = _read_secrets_toml().get("admin", {}).get("notify_email", "")
    return (email or os.environ.get("ADMIN_NOTIFY_EMAIL", "")).strip().lower()


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
        # Email fallback: link a pending invited profile on first sign-in.
        # Invitations store the email lower-cased, so normalise here too — a case
        # mismatch would otherwise miss the invite and (in self-serve) provision a
        # brand-new personal org instead of joining the invited one (A4).
        email_norm = (email or "").strip().lower()
        if email_norm:
            res = (
                client.table("user_profiles")
                .select("*")
                .eq("email", email_norm)
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
        updates["role"] = "operator"
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
    Access is admin-controlled: only invited users (pre-created profiles) and the
    configured gatekeeper email get in; anyone else is left in a pending state.
    """
    token = credentials.credentials if credentials else None
    user = get_user_from_token(token)
    if user:
        email = x_user_email or user.get("email") or ""
        profile = get_user_profile(user["id"], email=email, token=token)
        if profile:
            org_id = _ensure_org_for_profile(profile, email, user["id"])
            return {
                "user_id": user["id"],
                "email": email,
                "organization_id": org_id,
                "role": profile.get("role") or "operator",
                "token": token,
            }
        # No profile and no matching invite: auto-provision every new signed-in
        # user as super_admin with their own fresh organization. Self sign-up is
        # restricted at the Clerk instance level, so anyone who reaches here has
        # already been let through Clerk; each becomes the owner/admin of their
        # own tenant and can invite others into it.
        org_id = _create_super_admin_profile(user["id"], email)
        return {
            "user_id": user["id"],
            "email": email,
            "organization_id": org_id,
            "role": "super_admin",
            "token": token,
        }

    # No valid Clerk token. This path historically returned an anonymous
    # "operator" identity whose organization came straight from the client-
    # supplied X-Organization-Id header. Because the backend talks to Postgres as
    # service-role (RLS bypassed), that let an UNauthenticated caller read and
    # write any tenant's data just by guessing its org UUID — a cross-tenant IDOR
    # (CRIT-1 in the permissions review). We now fail closed: no verified user =>
    # 401, and tenancy is NEVER derived from a request header. The escape hatch
    # AUTHZ_FAIL_CLOSED=0 temporarily restores the legacy behavior for rollback
    # only; no server-to-server caller is known to rely on it.
    if os.environ.get("AUTHZ_FAIL_CLOSED", "1") != "0":
        raise HTTPException(status_code=401, detail="Authentication required.")
    return {
        "user_id": None,
        "organization_id": x_organization_id,
        "role": "operator",
        "token": None,
    }


def _ensure_permission(
    profile: dict,
    permission: str,
    *,
    detail: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    """Central authorization check: deny (403) unless the caller's role holds the
    atomic ``permission``. Emits a structured audit denial on failure. This is the
    single choke point that replaces the scattered inline role-string checks, so a
    new endpoint cannot silently ship without an explicit permission.

    Answers only *what* the role may do; data-scope (assigned org/project/site) is
    enforced separately at the query layer.
    """
    if has_permission(profile.get("role"), permission):
        return
    audit_denial(
        permission,
        actor_user_id=profile.get("user_id"),
        actor_role=profile.get("role"),
        organization_id=profile.get("organization_id"),
        target_type=target_type,
        target_id=target_id,
    )
    raise HTTPException(
        status_code=403,
        detail=detail or "You do not have permission to perform this action.",
    )


def _scope_enforcement_on() -> bool:
    """Phase 2 scope enforcement is OFF by default. Enabling it before every user
    has site/project assignments would lock people out, so it stays gated until
    backfill is done (PERMISSIONS_REVIEW_PACKAGE.md §8)."""
    return os.environ.get("SCOPE_ENFORCEMENT", "0") == "1"


def _effective_site_ids(profile: dict):
    """The caller's effective site-id scope, or ALL_SITES for org-wide access.

    Returns ALL_SITES (current org-wide behavior) whenever scope enforcement is
    disabled, so this is a no-op until SCOPE_ENFORCEMENT=1. Pure decision logic is
    in core/scope.py (unit-tested); this layer only fetches the assignment sets.
    """
    if not _scope_enforcement_on():
        return ALL_SITES
    role = profile.get("role")
    if role in ("super_admin", "auditor"):
        # Executive is org-wide; General Manager is read-only oversight across the
        # portfolio — business-unit narrowing is a later refinement, org-wide read
        # is acceptable and non-destructive for a read-only role.
        return ALL_SITES
    clerk_id, org = profile.get("user_id"), profile.get("organization_id")
    from db.queries import get_assigned_site_ids, get_project_site_ids
    if role == "admin":
        return resolve_site_scope(role, project_site_ids=get_project_site_ids(clerk_id, org))
    if role == "operator":
        return resolve_site_scope(role, assigned_site_ids=get_assigned_site_ids(clerk_id, org))
    return frozenset()  # pending/unknown -> no sites


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ReadingFields(BaseModel):
    ph:               float = Field(..., description="pH units (Limit: 6.0–9.0)")
    do:               float = Field(..., description="Dissolved oxygen mg/L (Limit: >4.0)")
    tss:              float = Field(..., description="Total suspended solids mg/L (Limit: <50)")
    turbidity:        float = Field(..., description="Turbidity NTU (Limit: <75)")
    cod:              float = Field(..., description="Chemical oxygen demand mg/L (Limit: <50)")
    ammonia:          float = Field(..., description="Ammonia as N mg/L (Limit: <5.0)")
    phosphate:        float = Field(..., description="Total phosphate mg/L (Limit: <5.0)")
    oil_grease:       float = Field(..., description="Oils & grease mg/L (Limit: <10)")
    ecoli:            float = Field(..., description="E. coli CFU/100mL (Limit: <200)")
    total_coliforms:  float = Field(..., description="Total coliforms CFU/100mL (Limit: <1000)")
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
    return {"status": "ok", "service": "lagoon-compliance-api", "version": get_version()}


@app.get("/version", tags=["System"])
def version():
    """Deployed version, commit SHA, and environment. Unauthenticated by design."""
    return get_version_info()


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
        # Phase 2: narrow to the caller's effective site scope (no-op while
        # SCOPE_ENFORCEMENT is off — returns ALL_SITES).
        scope = _effective_site_ids(profile)
        site_rows = sites_res.data if scope == ALL_SITES else [
            s for s in sites_res.data if s["id"] in scope
        ]
        if not site_rows:
            return {"sites": []}
        sites_res.data = site_rows
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
    _ensure_permission(profile, "sites.create", detail="Only admins can create sites.")
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
    _ensure_permission(profile, "sites.delete", detail="Only admins can delete sites.",
                       target_type="site", target_id=site_name)
    try:
        from db.queries import delete_site
        ok, msg, count = delete_site(
            site_name=site_name,
            organization_id=profile.get("organization_id"),
            token=profile["token"],
        )
        if not ok:
            raise HTTPException(status_code=404, detail=msg)
        audit_emit("site.delete", actor_user_id=profile.get("user_id"),
                   actor_role=profile.get("role"), organization_id=profile.get("organization_id"),
                   target_type="site", target_id=site_name, readings_deleted=count)
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
        "role": profile.get("role", "operator"),
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
    _ensure_permission(profile, "users.read", detail="Admin access required.")
    org_id = profile.get("organization_id")
    if not org_id:
        return {"users": []}
    from db.client import get_client as _gc
    client = _gc()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available.")
    try:
        profiles_res = (
            client.table("user_profiles")
            .select("id, email, role, created_at, clerk_id")
            .eq("organization_id", org_id)
            .execute()
        )
        users = [
            {
                "id": p["id"],
                "clerk_id": p.get("clerk_id"),
                "email": p.get("email") or "",
                "role": p["role"],
                "created_at": str(p.get("created_at") or ""),
                "last_sign_in": "",
                "provider": "email" if p.get("clerk_id") else "pending",
            }
            for p in (profiles_res.data or [])
        ]
        return {"users": users}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.patch("/users/{user_id}", tags=["Users"])
def update_user_role(user_id: str, body: UpdateRoleRequest, profile: dict = Depends(get_current_user_profile)):
    """Change a user's role. Admins can set operator/admin; only super_admin can grant super_admin."""
    _ensure_permission(profile, "users.role.assign", detail="Admin access required.",
                       target_type="user", target_id=user_id)
    if body.role not in ("operator", "admin", "auditor", "super_admin"):
        raise HTTPException(status_code=422, detail="Role must be operator, admin, auditor, or super_admin.")
    if body.role == "super_admin":
        _ensure_permission(profile, "users.executive.assign",
                           detail="Only super_admin can grant super_admin role.",
                           target_type="user", target_id=user_id)
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    client = _gc()
    # user_id is the profile row UUID; the caller is identified by Clerk ID, so
    # compare the target's clerk_id (not its UUID) to block self-role-changes.
    target = client.table("user_profiles").select("clerk_id").eq("id", user_id).eq("organization_id", org_id).execute()
    if not target.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    if target.data[0].get("clerk_id") == profile.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot change your own role.")
    res = client.table("user_profiles").update({"role": body.role}).eq("id", user_id).eq("organization_id", org_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    audit_emit("user.role.assign", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="user", target_id=user_id, new_role=body.role)
    return {"updated": True, "user_id": user_id, "role": body.role}


@app.delete("/users/{user_id}", tags=["Users"])
def remove_user(user_id: str, profile: dict = Depends(get_current_user_profile)):
    """Remove a user from the organisation (deletes their profile). Requires admin or super_admin."""
    _ensure_permission(profile, "users.remove", detail="Admin access required.",
                       target_type="user", target_id=user_id)
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    client = _gc()
    # Ensure target is in same org and not higher-ranked
    target = client.table("user_profiles").select("role, clerk_id").eq("id", user_id).eq("organization_id", org_id).execute()
    if not target.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    # user_id is the profile row UUID; the caller is identified by Clerk ID, so
    # compare the target's clerk_id (not its UUID) to block self-removal.
    if target.data[0].get("clerk_id") == profile.get("user_id"):
        raise HTTPException(status_code=400, detail="Cannot remove yourself.")
    target_role = target.data[0]["role"]
    if target_role == "super_admin" and profile.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Only super_admin can remove a super_admin.")
    # A3: never orphan an organisation by removing its last Executive Management
    # user. Count remaining super_admins in the org before deleting one.
    if target_role == "super_admin":
        sa = (client.table("user_profiles").select("id")
              .eq("organization_id", org_id).eq("role", "super_admin").execute())
        if len(sa.data or []) <= 1:
            raise HTTPException(
                status_code=409,
                detail="Cannot remove the last Executive Management user in the organisation.",
            )
    client.table("user_profiles").delete().eq("id", user_id).eq("organization_id", org_id).execute()
    audit_emit("user.remove", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="user", target_id=user_id, removed_role=target_role)
    return {"removed": True, "user_id": user_id}


class SiteAssignmentRequest(BaseModel):
    site_ids: list[str] = Field(default_factory=list, description="Site UUIDs to assign")


def _resolve_target_clerk_id(user_id: str, org_id: str) -> str:
    """Map a profile-row UUID to its Clerk id within the caller's org, or 404."""
    from db.client import get_client as _gc
    client = _gc()
    t = (client.table("user_profiles").select("clerk_id")
         .eq("id", user_id).eq("organization_id", org_id).execute())
    if not t.data:
        raise HTTPException(status_code=404, detail="User not found in your organisation.")
    clerk_id = t.data[0].get("clerk_id")
    if not clerk_id:
        raise HTTPException(status_code=409, detail="User has not completed sign-in yet.")
    return clerk_id


@app.get("/users/{user_id}/sites", tags=["Users"])
def get_user_sites(user_id: str, profile: dict = Depends(get_current_user_profile)):
    """List the site ids assigned to a user (Phase 2 scope administration)."""
    _ensure_permission(profile, "users.role.assign", detail="Admin access required.")
    org_id = profile.get("organization_id")
    clerk_id = _resolve_target_clerk_id(user_id, org_id)
    from db.queries import list_user_site_assignments
    return {"user_id": user_id, "site_ids": list_user_site_assignments(clerk_id, org_id)}


@app.put("/users/{user_id}/sites", tags=["Users"])
def put_user_sites(user_id: str, body: SiteAssignmentRequest,
                   profile: dict = Depends(get_current_user_profile)):
    """Replace a user's site assignments. Only org-owned site ids are accepted
    (server-side validated); the rest are ignored. Least-privilege delegation:
    requires users.role.assign (admin/super_admin)."""
    _ensure_permission(profile, "users.role.assign", detail="Admin access required.",
                       target_type="user", target_id=user_id)
    org_id = profile.get("organization_id")
    clerk_id = _resolve_target_clerk_id(user_id, org_id)
    from db.queries import set_user_site_assignments
    ok, msg = set_user_site_assignments(
        clerk_id, body.site_ids, org_id, assigned_by=profile.get("user_id"))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    audit_emit("user.sites.assign", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="user", target_id=user_id, site_count=len(body.site_ids))
    return {"updated": True, "user_id": user_id, "message": msg}


def _require_clerk_secret_key() -> str:
    """Resolve the Clerk secret key, refusing when it targets a different instance
    than the one we verify logins against.

    The secret key decides which Clerk instance an invitation is created on, while
    the publishable key decides which instance we verify logins against. If they
    disagree, a local invite would create an account on the live instance that
    still could not log in here — so refuse rather than write to the wrong tenant.
    """
    sk = _clerk_secret_key()
    if not sk:
        raise HTTPException(
            status_code=503,
            detail="Clerk secret key not configured (CLERK_SECRET_KEY). Cannot invite users.",
        )
    pk_instance = _clerk_key_instance(_clerk_publishable_key())
    sk_instance = _clerk_key_instance(sk)
    if pk_instance and sk_instance and pk_instance != sk_instance:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Clerk key mismatch: verifying logins against the '{pk_instance}' "
                f"instance but the secret key targets '{sk_instance}'. Set "
                f"clerk.dev_secret_key (sk_{pk_instance}_…) in .streamlit/secrets.toml "
                f"to invite users against the '{pk_instance}' instance."
            ),
        )
    return sk


def _create_clerk_invitation(email: str, role: str, org_id: str | None, redirect_url: str) -> str:
    """Create a Clerk invitation. Clerk emails the recipient a magic link; on
    acceptance they set their own password and a Clerk user is created, with the
    invitation's public_metadata copied onto it. Returns the invitation ID.

    Invitations bypass the instance's restricted sign-up mode, which is the whole
    point — this is how new accounts are made.
    """
    sk = _require_clerk_secret_key()
    import httpx as _httpx
    body: dict = {
        "email_address": email,
        "public_metadata": {"role": role, "org_id": org_id},
        "notify": True,
    }
    if redirect_url:
        body["redirect_url"] = redirect_url
    r = _httpx.post(
        "https://api.clerk.com/v1/invitations",
        headers={"Authorization": f"Bearer {sk}"},
        json=body,
        timeout=10,
    )
    if r.status_code not in (200, 201):
        try:
            msg = r.json()["errors"][0]["message"]
        except Exception:
            msg = r.text[:200]
        raise HTTPException(status_code=502, detail=f"Clerk invitation failed: {msg}")
    return r.json()["id"]


@app.post("/users/invite", tags=["Users"], status_code=201)
def invite_user(body: InviteRequest, request: Request, profile: dict = Depends(get_current_user_profile)):
    """
    Admin-controlled account creation via Clerk invitations. Clerk emails the
    recipient a magic link; they set their own password and their account is
    created on acceptance. A pending profile row (clerk_id null) carrying the
    assigned role + organisation is inserted now and linked by email on their
    first sign-in (see get_user_profile's email fallback).
    """
    _ensure_permission(profile, "users.invite", detail="Admin access required.")
    if body.role not in ("operator", "admin", "auditor", "super_admin"):
        raise HTTPException(status_code=422, detail="Invalid role.")
    if body.role == "super_admin":
        _ensure_permission(profile, "users.executive.assign",
                           detail="Only super_admin can invite as super_admin.")
    org_id = profile.get("organization_id")
    from db.client import get_client as _gc
    import uuid as _uuid
    client = _gc()
    if not client:
        raise HTTPException(status_code=503, detail="Database not available.")
    email = body.email.strip().lower()
    # Send the invitation back to this app's origin so Clerk's ticket lands on the
    # sign-up flow (falls back to the API's own base URL if no Origin header).
    origin = request.headers.get("origin") or str(request.base_url)
    redirect_url = origin.rstrip("/") + "/"
    try:
        existing = client.table("user_profiles").select("id").eq("email", email).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail=f"{email} is already invited or registered.")
        invitation_id = _create_clerk_invitation(email, body.role, org_id, redirect_url)
        client.table("user_profiles").insert({
            "id": str(_uuid.uuid4()),
            "organization_id": org_id,
            "role": body.role,
            "email": email,
            "clerk_id": None,  # linked on first sign-in via the email fallback
        }).execute()
        return {
            "invited": True,
            "email": email,
            "role": body.role,
            "invitation_id": invitation_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Access requests (public) ──────────────────────────────────────────────────

class AccessRequest(BaseModel):
    email: str
    name: str = ""
    message: str = ""


def _send_admin_email(subject: str, body_text: str) -> bool:
    """Email the gatekeeper address via SMTP ([smtp] in secrets.toml or SMTP_* envs).
    Returns False (after logging the message) when SMTP is not configured."""
    to_addr = _admin_notify_email()
    if not to_addr:
        print(f"[access-request] ADMIN_NOTIFY_EMAIL not set; dropping notification:\n{body_text}", file=sys.stderr)
        return False
    smtp_cfg = _read_secrets_toml().get("smtp", {})
    host = smtp_cfg.get("host") or os.environ.get("SMTP_HOST", "")
    if not host:
        print(f"[access-request] SMTP not configured; request for admin ({to_addr}):\n{body_text}", file=sys.stderr)
        return False
    port = int(smtp_cfg.get("port") or os.environ.get("SMTP_PORT", "587"))
    user = smtp_cfg.get("user") or os.environ.get("SMTP_USER", "")
    password = smtp_cfg.get("password") or os.environ.get("SMTP_PASS", "")
    from_addr = smtp_cfg.get("from") or os.environ.get("SMTP_FROM", user or to_addr)
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body_text)
    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls()
            if user:
                s.login(user, password)
            s.send_message(msg)
        return True
    except Exception as exc:
        print(f"[access-request] SMTP send failed: {exc}\n{body_text}", file=sys.stderr)
        return False


@app.post("/access-request", tags=["Auth"], status_code=202)
def request_access(body: AccessRequest):
    """Public endpoint: a would-be user asks for access. The gatekeeper admin is
    notified by email and then creates the account (which generates the random
    password they pass on to the user)."""
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Valid email required.")
    text = (
        "New access request for Dubai Lagoons.\n\n"
        f"Email:   {email}\n"
        f"Name:    {body.name.strip() or '-'}\n"
        f"Message: {body.message.strip()[:500] or '-'}\n\n"
        "To grant access: sign in as admin -> Settings -> User Management -> Invite User.\n"
        "A one-time password will be generated for you to send to them."
    )
    _send_admin_email("Dubai Lagoons — access request", text)
    return {"requested": True}


# ── Billing ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    success_url: str
    cancel_url: str

class PortalRequest(BaseModel):
    return_url: str


@app.get("/billing/status", tags=["Billing"])
def billing_status(profile: dict = Depends(get_current_user_profile)):
    """Return current plan, site usage, and whether payments are configured.
    Requires billing.read — subscription/financial visibility starts at the
    Project/Contract Manager tier (PERMISSIONS_MATRIX.md row 73); Site Supervisors
    and (read-only) General Managers do not see billing.
    """
    _ensure_permission(profile, "billing.read",
                       detail="Your role does not have access to billing information.")
    from billing import (
        get_org_billing, count_sites, PLANS, is_configured,
        has_subscription, provider_name, supports_portal,
    )
    configured = is_configured()
    common = {
        "payment_provider":   provider_name(),
        "payments_configured": configured,
        "portal_available":   supports_portal(),
        "available_plans":    PLANS,
    }
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
            **common,
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
        "has_subscription":  has_subscription(billing),
        "subscription_status": billing.get("subscription_status"),
        **common,
    }


@app.post("/billing/checkout", tags=["Billing"])
def billing_checkout(body: CheckoutRequest, profile: dict = Depends(get_current_user_profile)):
    """Create a hosted checkout session with the payment provider and return the redirect URL."""
    _ensure_permission(profile, "billing.manage", detail="Admin access required.")
    from billing import create_checkout_session, is_configured, PLANS
    if not is_configured():
        raise HTTPException(status_code=503, detail="Payments are not configured. Add your payment provider keys to secrets.toml.")
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
        raise HTTPException(status_code=500, detail=f"Could not create a checkout session for plan '{body.plan}'.")
    return {"checkout_url": url}


@app.post("/billing/portal", tags=["Billing"])
def billing_portal(body: PortalRequest, profile: dict = Depends(get_current_user_profile)):
    """Create a hosted billing-portal session for plan/payment management
    (only for providers that offer one)."""
    _ensure_permission(profile, "billing.manage", detail="Admin access required.")
    from billing import create_portal_session, is_configured, supports_portal
    if not is_configured():
        raise HTTPException(status_code=503, detail="Payments are not configured.")
    if not supports_portal():
        raise HTTPException(
            status_code=400,
            detail="The current payment provider does not offer a hosted billing portal.",
        )
    org_id = profile.get("organization_id", "")
    url = create_portal_session(org_id=org_id, return_url=body.return_url)
    if not url:
        raise HTTPException(
            status_code=400,
            detail="No customer record found with the payment provider. Complete a checkout first.",
        )
    return {"portal_url": url}


@app.post("/billing/cancel", tags=["Billing"])
def billing_cancel(profile: dict = Depends(get_current_user_profile)):
    """Cancel the organization's subscription and downgrade to the starter plan."""
    _ensure_permission(profile, "billing.manage", detail="Admin access required.")
    from billing import cancel_subscription, get_org_billing, has_subscription, is_configured
    if not is_configured():
        raise HTTPException(status_code=503, detail="Payments are not configured.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")
    if not has_subscription(get_org_billing(org_id)):
        raise HTTPException(status_code=400, detail="No active subscription to cancel.")
    if not cancel_subscription(org_id):
        raise HTTPException(status_code=500, detail="Cancellation failed. Try again or contact support.")
    return {"cancelled": True}


@app.post("/billing/webhook", tags=["Billing"], include_in_schema=False)
async def billing_webhook(request: Request):
    """Payment provider webhook — updates org plan and site_limit on
    subscription/payment events. The active provider verifies its own
    signature header (e.g. stripe-signature, cko-signature)."""
    from billing import handle_webhook, is_configured
    if not is_configured():
        raise HTTPException(status_code=503, detail="Payments are not configured.")
    payload = await request.body()
    result = handle_webhook(payload, dict(request.headers))
    if not result.get("handled") and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"received": True, "event_type": result.get("event_type")}


@app.post("/assess", tags=["Compliance"])
def assess(body: AssessRequest, _=Security(_check_key)):
    """Check a set of readings against compliance limits and the alert engine.
    Does NOT save to the database — use this to validate before logging,
    or when a field team just wants a quick compliance check.
    """
    reading = _build_reading(body)
    return _assess(reading)


@app.post("/log", tags=["Compliance"])
def log_reading(body: LogRequest, _=Security(_check_key), profile: dict = Depends(get_current_user_profile)):
    """Save a monthly reading for a site, then return the full Compliance
    compliance assessment, alert level, and treatment response.
    Enforces role validation and tenant data isolation.
    """
    _ensure_permission(profile, "readings.create",
                       detail="User role does not have permission to log water readings.")

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


# ── Sludge & sediment ─────────────────────────────────────────────────────────

class SludgeZoneRequest(BaseModel):
    zone_name:      str   = Field(..., min_length=1, max_length=80)
    total_depth_m:  float = Field(..., gt=0, description="Total water column depth (m)")
    sludge_depth_m: float = Field(..., ge=0, description="Accumulated sludge depth (m)")
    survey_date:    Optional[str] = Field(None, description="ISO date of the survey (YYYY-MM-DD)")


@app.get("/sludge/{site}", tags=["Sludge"])
def list_sludge_zones(site: str, profile: dict = Depends(get_current_user_profile)):
    """Return the sludge survey zones for a site, each with derived capacity metrics."""
    from db.queries import get_sludge_zones
    zones = get_sludge_zones(site, organization_id=profile.get("organization_id"), token=profile.get("token"))
    return {"site": site, "zones": zones}


@app.post("/sludge/{site}", tags=["Sludge"], status_code=201)
def save_sludge_zone(site: str, body: SludgeZoneRequest, profile: dict = Depends(get_current_user_profile)):
    """Add or update a sludge zone survey for a site. Requires operator/admin/super_admin."""
    _ensure_permission(profile, "sludge.write", detail="Your role cannot record sludge surveys.",
                       target_type="site", target_id=site)
    if body.sludge_depth_m > body.total_depth_m:
        raise HTTPException(status_code=422, detail="Sludge depth cannot exceed total depth.")
    from db.queries import upsert_sludge_zone
    ok, msg = upsert_sludge_zone(
        site, body.zone_name.strip(), body.total_depth_m, body.sludge_depth_m,
        survey_date=body.survey_date,
        organization_id=profile.get("organization_id"), token=profile.get("token"),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"saved": True, "message": msg, "zone_name": body.zone_name.strip()}


@app.delete("/sludge/{site}/{zone_name}", tags=["Sludge"])
def remove_sludge_zone(site: str, zone_name: str, profile: dict = Depends(get_current_user_profile)):
    """Delete a sludge zone from a site. Requires operator/admin/super_admin."""
    _ensure_permission(profile, "sludge.delete", detail="Your role cannot delete sludge surveys.",
                       target_type="sludge_zone", target_id=f"{site}/{zone_name}")
    from db.queries import delete_sludge_zone
    ok, msg = delete_sludge_zone(
        site, zone_name,
        organization_id=profile.get("organization_id"), token=profile.get("token"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    audit_emit("sludge.delete", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile.get("organization_id"),
               target_type="sludge_zone", target_id=f"{site}/{zone_name}")
    return {"deleted": True, "message": msg}


@app.get("/readings/{site}", tags=["Compliance"])
def site_readings(site: str, year: int = 2026, _=Security(_check_key), profile: dict = Depends(get_current_user_profile)):
    """Return the raw monthly readings for a site (all 14 parameters per month),
    ordered by month. Drives the live Water Quality Monitoring data log."""
    try:
        from db.queries import get_readings_for_site
        readings = get_readings_for_site(site, year=year, organization_id=profile["organization_id"], token=profile["token"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    rows = [
        {
            "month":           r.timestamp.month,
            "month_name":      MONTH_NAMES[r.timestamp.month - 1],
            "ph":              r.ph,
            "do":              r.do,
            "tss":             r.tss,
            "turbidity":       r.turbidity,
            "cod":             r.cod,
            "ammonia":         r.ammonia,
            "phosphate":       r.phosphate,
            "oil_grease":      r.oil_grease,
            "ecoli":           r.ecoli,
            "total_coliforms": r.total_coliforms,
            "chla":            r.chla,
            "phycocyanin":     r.phycocyanin,
            "salinity":        r.salinity,
            "water_temp":      r.water_temp,
        }
        for r in sorted(readings, key=lambda x: x.timestamp.month)
    ]
    return {"site": site, "year": year, "rows": rows}


@app.get("/community/{site}", tags=["Science"])
def site_community(site: str, year: int = 2026, profile: dict = Depends(get_current_user_profile)):
    """Predict the favoured algae community/type and ecological succession stage
    for a site from its most recent stored reading. Recommends a confirmatory
    lab test when conditions favour cyanobacteria."""
    try:
        from db.queries import get_readings_for_site
        readings = get_readings_for_site(site, year=year,
                                         organization_id=profile.get("organization_id"),
                                         token=profile.get("token"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not readings:
        return {"site": site, "available": False,
                "message": "No readings yet — log a lab report to get an algae & bloom forecast."}

    latest = max(readings, key=lambda r: r.timestamp.month)
    from dataclasses import asdict
    from science.community import classify_community
    forecast = classify_community(
        temperature=latest.water_temp, dissolved_oxygen=latest.do,
        ammonia=latest.ammonia, phosphate=latest.phosphate,
        chla=latest.chla, phycocyanin=latest.phycocyanin, salinity=latest.salinity,
    )
    return {
        "site": site,
        "available": True,
        "period": f"{MONTH_NAMES[latest.timestamp.month - 1]} {latest.timestamp.year}",
        "forecast": asdict(forecast),
    }


class DataRequestBody(BaseModel):
    items:  list[str] = Field(..., min_length=1, description="Parameters / tests to request")
    reason: str = Field("", max_length=500)


@app.get("/community/{site}/requests", tags=["Science"])
def list_data_requests(site: str, profile: dict = Depends(get_current_user_profile)):
    """List open data/lab requests for a site."""
    from db.queries import get_open_data_requests
    reqs = get_open_data_requests(site, organization_id=profile.get("organization_id"),
                                  token=profile.get("token"))
    return {"site": site, "requests": reqs}


@app.post("/community/{site}/requests", tags=["Science"], status_code=201)
def create_data_request_endpoint(site: str, body: DataRequestBody,
                                 profile: dict = Depends(get_current_user_profile)):
    """Create an open data/lab request for a site. Requires operator/admin/super_admin."""
    _ensure_permission(profile, "requests.create", detail="Your role cannot raise requests.",
                       target_type="site", target_id=site)
    from db.queries import create_data_request
    ok, msg, row = create_data_request(
        site, [i.strip() for i in body.items if i.strip()], reason=body.reason,
        organization_id=profile.get("organization_id"), token=profile.get("token"),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"created": True, "message": msg, "request": row}


@app.delete("/community/{site}/requests/{request_id}", tags=["Science"])
def dismiss_data_request_endpoint(site: str, request_id: str,
                                  profile: dict = Depends(get_current_user_profile)):
    """Mark a data/lab request fulfilled. Requires operator/admin/super_admin."""
    _ensure_permission(profile, "requests.fulfil", detail="Your role cannot update requests.",
                       target_type="request", target_id=request_id)
    from db.queries import dismiss_data_request
    ok, msg = dismiss_data_request(request_id, site,
                                   organization_id=profile.get("organization_id"),
                                   token=profile.get("token"))
    if not ok:
        raise HTTPException(status_code=404, detail=msg)
    return {"fulfilled": True, "message": msg}


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
                "description": "Check water quality values against compliance limits. No save.",
                "endpoint": "POST /assess",
                "input_schema": AssessRequest.model_json_schema(),
            },
            {
                "name": "log_reading",
                "description": "Save a monthly reading and return compliance + alert level.",
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
    Returns the 14 Compliance parameters as JSON. Human review is required before saving.
    """
    # Gate before spending Anthropic credits. Require a real signed-in user
    # (the resolver now fails closed on no token, but keep the explicit check as
    # defense in depth), then require readings.create — uploading/extracting a
    # lab report is a data-entry action, so the read-only General Manager
    # (auditor) is excluded (PERMISSIONS_MATRIX.md row 39; M5).
    if not profile.get("user_id"):
        raise HTTPException(status_code=401, detail="Sign in to extract lab reports.")
    _ensure_permission(profile, "readings.create",
                       detail="Your role may not upload or extract lab reports.")
    from extract import extract_lab_report, is_configured
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI extraction needs an Anthropic API key. Add it under [anthropic] api_key in .streamlit/secrets.toml (or set the ANTHROPIC_API_KEY env var), then try the upload again.",
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
def download_compliance_report(
    site: str,
    year: int = 2026,
    draft: bool = True,
    profile: dict = Depends(get_current_user_profile),
):
    """Generate a compliance PDF for the given site and year.
    Pass ?draft=false for a clean (watermark-free) official report.
    Returns application/pdf as an attachment download.
    """
    # CRIT-3: the non-draft PDF is the auditable regulatory artifact. Draft
    # previews need only reports.generate_draft; the clean official export
    # requires reports.approve_final (managers/GM/executive), separating routine
    # generation from regulatory sign-off. The ?draft flag is client-controlled,
    # so it selects the *required permission* here rather than acting as a gate.
    required = "reports.generate_draft" if draft else "reports.approve_final"
    _ensure_permission(
        profile, required,
        detail=("Your role may not export the final regulatory report."
                if not draft else "Your role may not generate compliance reports."),
        target_type="report", target_id=f"{site}/{year}",
    )
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
        from reporting import build_compliance_report
        pdf_bytes = build_compliance_report(site, year, readings, draft=draft)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {exc}")

    suffix = "_DRAFT" if draft else ""
    filename = f"Compliance_{site}_{year}{suffix}.pdf"
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

# index.html must never be cached: it is the entry point that references the
# content-hashed JS/CSS bundles, and each build mints new hashes and deletes the
# old ones. A browser holding a stale index.html would request a deleted bundle
# and keep running old code until a hard refresh — so always revalidate it.
# (The hashed assets themselves are immutable and safe to cache long-term.)
_INDEX_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _index_response() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers=_INDEX_NO_CACHE)


@app.get("/{catchall:path}")
def serve_react_app(catchall: str):
    # Prevent accessing files outside of FRONTEND_DIR for security
    # Clean the path to avoid directory traversal
    safe_path = os.path.normpath(catchall).lstrip(os.path.sep)
    if safe_path.startswith("..") or safe_path.startswith("/") or safe_path.startswith("\\"):
        return _index_response()

    # Check if the requested file exists in frontend/dist (like favicon.svg, icons.svg)
    file_path = os.path.join(FRONTEND_DIR, safe_path)
    if safe_path and os.path.isfile(file_path):
        return FileResponse(file_path)

    # Otherwise return index.html for React router
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return _index_response()

    return {"message": "React frontend is not built. Please run 'npm run build' inside frontend directory."}

