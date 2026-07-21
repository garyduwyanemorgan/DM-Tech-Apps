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

from fastapi import FastAPI, HTTPException, Security, Header, Depends, UploadFile, File, Form, Request
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
from core.config import secret
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

    Only ever set via CLERK_DEV_PUBLISHABLE_KEY (.env) or secrets.toml, neither
    of which exists on Render — so a value here means we are running locally and
    should authenticate against the dev instance. A live publishable key is bound
    to its registered domain and Clerk rejects it on localhost.
    """
    return secret("clerk", "dev_publishable_key")


def _clerk_publishable_key() -> str:
    """Resolve the Clerk publishable key. A configured dev key wins.

    This key also selects which instance's JWKS tokens are verified against
    (_clerk_jwks_url), so it must name the same instance the frontend signed the
    user in with — otherwise every authenticated request 401s.
    """
    return _clerk_dev_publishable_key() or secret("clerk", "publishable_key")


def _clerk_secret_key() -> str:
    """Clerk Backend API secret key.

    Mirrors _clerk_publishable_key: a configured dev secret key wins, so Backend
    API writes land on the same instance we verify tokens against.
    """
    dev_sk = secret("clerk", "dev_secret_key")
    if dev_sk and _clerk_dev_publishable_key():
        return dev_sk
    return secret("clerk", "secret_key")


def _clerk_key_instance(key: str) -> str:
    """'test', 'live', or '' — which Clerk instance a pk_/sk_ key belongs to."""
    for instance in ("test", "live"):
        if key.startswith(f"pk_{instance}_") or key.startswith(f"sk_{instance}_"):
            return instance
    return ""


def _admin_notify_email() -> str:
    """The single gatekeeper email address. New-user access requests are sent here,
    and only this address is allowed to bootstrap itself as super_admin."""
    return secret("admin", "notify_email").lower()


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
                # Tolerates the column being absent until 006_sample_data_pref.sql is run.
                "show_sample_data": profile.get("show_sample_data", True),
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
            "show_sample_data": True,
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


_DEMO_STATE_TTL_SECONDS = 60
_demo_state_cache: dict = {}  # org_id -> (fetched_monotonic, state | None)


def _demo_state(org_id: str | None):
    """The org's demo state, or None for orgs that never activated a demo or
    that hold a live subscription (a subscription supersedes demo entirely —
    that is the one-click "switch to live"). Cached ~60s per org, so demo
    checks don't add a DB round-trip to every write request.
    """
    if not org_id:
        return None
    import time as _time
    cached = _demo_state_cache.get(org_id)
    if cached and _time.monotonic() - cached[0] < _DEMO_STATE_TTL_SECONDS:
        return cached[1]
    from core.demo import demo_status
    from db.queries import get_demo_key
    from billing import get_org_billing, has_subscription
    state = None
    row = get_demo_key(org_id)
    if row and not has_subscription(get_org_billing(org_id)):
        state = {
            **demo_status(row.get("expires_at")),
            "activated_at": row.get("activated_at"),
            "expires_at": row.get("expires_at"),
        }
    _demo_state_cache[org_id] = (_time.monotonic(), state)
    return state


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
    enforced separately at the query layer. An org whose demo has expired (and
    that has not gone live) is read-only: writes 402 here, billing stays open.
    """
    if has_permission(profile.get("role"), permission):
        from core.demo import blocked_when_demo_expired
        if blocked_when_demo_expired(permission):
            demo = _demo_state(profile.get("organization_id"))
            if demo and demo["expired"]:
                raise HTTPException(
                    status_code=402,
                    detail=("Your one-month demo has ended and the system is now "
                            "read-only. Choose a plan in Settings to switch to live — "
                            "everything you set up during the demo carries over."),
                )
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
    address:            str | None = Field(None, max_length=300, description="Street address — pinned on the site map")


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
        # Query 1: all sites for this org. The address column arrives with
        # migration 015 — retry without it so an unapplied migration degrades
        # to address-less sites instead of an empty list.
        try:
            sites_res = client.table("sites").select("id, name, address").eq("organization_id", org_id).execute()
        except Exception:
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
        sites = [{"id": s["id"], "name": s["name"], "address": s.get("address"),
                  "reading_count": counts.get(s["id"], 0)} for s in sites_res.data]
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

    # ── Billing: enforce site limit (waived while a demo is active — the demo
    # is unlimited so prospects can test end-to-end; expiry is the control) ────
    from billing import get_org_billing, count_sites, PLANS
    demo = _demo_state(org_id)
    billing = get_org_billing(org_id)
    site_limit = billing.get("site_limit", 1)
    current_count = count_sites(org_id)
    if (demo is None or not demo["active"]) and current_count >= site_limit:
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
            address=(body.address or "").strip() or None,
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
        "show_sample_data": profile.get("show_sample_data", True),
        "pending": profile.get("organization_id") is None and profile.get("user_id") is not None,
    }


class PreferencesRequest(BaseModel):
    show_sample_data: bool


@app.patch("/profile/preferences", tags=["Auth"])
def update_preferences(
    body: PreferencesRequest,
    profile: dict = Depends(get_current_user_profile),
):
    """Persist the signed-in user's display preferences against their profile, so the
    setting follows them across browsers and devices rather than living in localStorage.
    """
    user_id = profile.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to change preferences.")

    try:
        from db.client import get_client
        # Unscoped client, as every other user_profiles write does. Supabase cannot decode
        # a Clerk JWT (PostgREST answers PGRST301 "no suitable key"), so the token is not
        # passed. Safe here because the row is pinned to the clerk_id that came out of the
        # verified token — a caller can only ever update their own profile.
        client = get_client()
        client.table("user_profiles").update(
            {"show_sample_data": body.show_sample_data}
        ).eq("clerk_id", user_id).execute()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save preference: {exc}")

    return {"show_sample_data": body.show_sample_data}


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
        # One batched query for the whole org's site assignments (keyed by
        # clerk_id) so the Sites column doesn't need a request per user.
        assignments: dict[str, list[str]] = {}
        try:
            asg = (client.table("user_site_assignments")
                   .select("user_clerk_id, site_id")
                   .eq("organization_id", org_id).execute())
            for row in (asg.data or []):
                assignments.setdefault(row["user_clerk_id"], []).append(row["site_id"])
        except Exception:
            pass  # column degrades to empty; assignments UI still loads per-user
        users = [
            {
                "id": p["id"],
                "clerk_id": p.get("clerk_id"),
                "email": p.get("email") or "",
                "role": p["role"],
                "created_at": str(p.get("created_at") or ""),
                "last_sign_in": "",
                "provider": "email" if p.get("clerk_id") else "pending",
                "site_ids": assignments.get(p.get("clerk_id") or "", []),
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
    _ensure_permission(profile, "users.read", detail="Admin access required.")
    org_id = profile.get("organization_id")
    clerk_id = _resolve_target_clerk_id(user_id, org_id)
    from db.queries import list_user_site_assignments
    return {"user_id": user_id, "site_ids": list_user_site_assignments(clerk_id, org_id)}


@app.put("/users/{user_id}/sites", tags=["Users"])
def put_user_sites(user_id: str, body: SiteAssignmentRequest,
                   profile: dict = Depends(get_current_user_profile)):
    """Replace a user's site assignments. Only org-owned site ids are accepted
    (server-side validated); the rest are ignored. Site assignments decide what
    a user can work on, so only Executive Management may change them."""
    _ensure_permission(profile, "users.sites.assign",
                       detail="Only Executive Management can manage site assignments.",
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
                f"CLERK_DEV_SECRET_KEY (sk_{pk_instance}_…) in .env "
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
    """Email the gatekeeper address via SMTP (SMTP_* env vars, .env, or [smtp] in
    secrets.toml). Returns False (after logging the message) when SMTP is not configured."""
    to_addr = _admin_notify_email()
    if not to_addr:
        print(f"[access-request] ADMIN_NOTIFY_EMAIL not set; dropping notification:\n{body_text}", file=sys.stderr)
        return False
    host = secret("smtp", "host")
    if not host:
        print(f"[access-request] SMTP not configured; request for admin ({to_addr}):\n{body_text}", file=sys.stderr)
        return False
    port = int(secret("smtp", "port") or "587")
    user = secret("smtp", "user")
    password = secret("smtp", "password")
    from_addr = secret("smtp", "from") or user or to_addr
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


@app.get("/demo/status", tags=["Demo"])
def demo_status_endpoint(profile: dict = Depends(get_current_user_profile)):
    """The org's demo state: whether a demo can be activated, is running (with
    days left), or has expired. Any authenticated member may read it."""
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")
    from billing import get_org_billing, has_subscription
    subscribed = has_subscription(get_org_billing(org_id))
    from db.queries import get_demo_key
    row = get_demo_key(org_id)
    if not row:
        return {"exists": False, "active": False, "expired": False, "days_left": 0,
                "activated_at": None, "expires_at": None,
                "has_subscription": subscribed, "can_activate": not subscribed}
    from core.demo import demo_status
    st = demo_status(row.get("expires_at"))
    return {"exists": True, **st,
            "activated_at": row.get("activated_at"), "expires_at": row.get("expires_at"),
            "has_subscription": subscribed, "can_activate": False}


@app.post("/demo/activate", tags=["Demo"], status_code=201)
def activate_demo(profile: dict = Depends(get_current_user_profile)):
    """One-click demo activation. Provisions the org's demo key server-side
    (the user never sees or enters it) and starts the one-month clock. One demo
    per organisation, ever; Executive Management only."""
    _ensure_permission(profile, "demo.activate",
                       detail="Only Executive Management can activate the demo.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")
    from billing import get_org_billing, has_subscription
    if has_subscription(get_org_billing(org_id)):
        raise HTTPException(status_code=409, detail="This organisation is already on a live plan.")
    from db.queries import create_demo_key, get_demo_key
    if get_demo_key(org_id):
        raise HTTPException(status_code=409, detail="This organisation has already used its demo.")
    row, msg = create_demo_key(org_id, activated_by=profile.get("user_id"))
    if not row:
        raise HTTPException(status_code=500, detail=msg)
    _demo_state_cache.pop(org_id, None)
    audit_emit("demo.activate", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               expires_at=row.get("expires_at"))
    from core.demo import demo_status
    return {"activated": True, **demo_status(row.get("expires_at")),
            "activated_at": row.get("activated_at"), "expires_at": row.get("expires_at")}


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
        raise HTTPException(status_code=503, detail="Payments are not configured. Set the provider's *_SECRET_KEY environment variable.")
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
    report_type: str = Form(""),
    profile: dict = Depends(get_current_user_profile),
):
    """Parse an uploaded lab report into a structured, gated LabSample.

    Wimpey Laboratories PDFs are parsed deterministically from their text layer;
    scanned reports fall back to Claude vision at low confidence. Either way the
    result comes back with `reviewer_status: pending` and is NOT persisted — a
    human approves it before it becomes data (assurance gateway, gate 6).

    `report_type` is what the user selected in the upload dropdown. When the
    certificate itself declares a different type, both are returned in
    `type_conflict` and neither is applied — the user reconciles it. Silently
    preferring either one would let a certificate be filed, and later judged,
    against the wrong specification set.
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

    content = await file.read()
    media_type = file.content_type or "application/pdf"
    from ingestion.router import ingest
    try:
        # Parsing (and any vision fallback) is blocking — run it off the event
        # loop so one extraction doesn't freeze every other request.
        from fastapi.concurrency import run_in_threadpool
        sample = await run_in_threadpool(ingest, content, media_type, file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except RuntimeError as exc:
        # Raised when the scanned-report fallback has no Anthropic key configured.
        raise HTTPException(status_code=503, detail=str(exc))

    audit_emit("lab_report.extract", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile.get("organization_id"),
               target_type="lab_report", target_id=sample.report_no,
               report_type=sample.report_type, extraction_method=sample.extraction_method,
               parameters=len(sample.results), anomalies=len(sample.anomalies))

    # mode="json" so dates serialise to ISO strings and enums to their values.
    payload = sample.model_dump(mode="json")
    payload["selected_report_type"] = (report_type or "").strip()
    payload["type_conflict"] = _type_conflict(
        selected=report_type, detected=sample.report_type,
        organization_id=profile.get("organization_id"),
    )
    return payload


def _type_conflict(selected: str, detected: str, organization_id: str | None) -> dict | None:
    """Describe a disagreement between the chosen and the declared report type.

    Returns None when they agree, when nothing was selected, or when the document
    declared nothing to disagree with (a scan carries no form code). A conflict is
    reported, never resolved here: the two may belong to different specification
    scopes, and picking one silently would decide which limits later apply.
    """
    from core.report_types import get_builtin

    chosen = (selected or "").strip()
    if not chosen or not detected or detected == "scanned":
        return None
    if chosen.lower() == detected.lower():
        return None

    detected_label = (get_builtin(detected) or {}).get("label", detected)

    return {
        "selected": chosen,
        "selected_label": (get_builtin(chosen) or {}).get("label", chosen),
        "detected": detected,
        "detected_label": detected_label,
        # Scope is a property of the asset, not of the analysis, so a type
        # mismatch alone cannot say whether specifications differ.
        "message": (
            f"You selected “{(get_builtin(chosen) or {}).get('label', chosen)}”, but this "
            f"certificate declares itself as “{detected_label}”."
        ),
    }


class CreateReportTypeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80, description="Report type name")


@app.get("/report-types", tags=["Upload"])
def list_report_types_endpoint(profile: dict = Depends(get_current_user_profile)):
    """Report types offered in the upload dropdown: built-ins plus this org's own."""
    from core.report_types import BUILTIN_REPORT_TYPES
    from db.queries import list_custom_report_types

    org_id = profile.get("organization_id")
    custom = list_custom_report_types(org_id) if org_id else []
    return {
        "types": list(BUILTIN_REPORT_TYPES) + [
            {"key": t["name"], "label": t["name"], "builtin": False}
            for t in custom
        ]
    }


@app.post("/report-types", tags=["Upload"], status_code=201)
def create_report_type_endpoint(body: CreateReportTypeRequest,
                                profile: dict = Depends(get_current_user_profile)):
    """Add an organisation-defined report type.

    A name and nothing else. Fields come from whatever the extraction finds, so
    the certificate stays the source of truth. Scope is deliberately not asked for
    here: it belongs to the asset a certificate is about, not to the analysis
    performed on it (see core/assets.py).
    """
    _ensure_permission(profile, "readings.create",
                       detail="Your role may not add report types.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")

    from core.report_types import BUILTIN_REPORT_TYPES, normalise_name
    from db.queries import create_report_type, list_custom_report_types

    name = normalise_name(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Report type name cannot be blank.")

    taken = {t["key"].lower() for t in BUILTIN_REPORT_TYPES}
    taken |= {t["label"].lower() for t in BUILTIN_REPORT_TYPES}
    taken |= {(t.get("name") or "").lower() for t in list_custom_report_types(org_id)}
    if name.lower() in taken:
        raise HTTPException(status_code=409, detail=f"Report type '{name}' already exists.")

    try:
        row = create_report_type(org_id, name, created_by=profile.get("user_id"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create report type: {exc}")
    if not row:
        raise HTTPException(
            status_code=503,
            detail="Report types are not available — migration 017 may not be applied.",
        )

    audit_emit("report_type.create", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="report_type", target_id=name)
    return {"key": name, "label": name, "builtin": False}


class SaveLabSampleRequest(BaseModel):
    sample:      dict       = Field(..., description="The reviewed LabSample")
    results:     list[dict] = Field(default_factory=list, description="Confirmed parameter rows")
    site:        str | None = Field(None, description="Site name to attach the certificate to")
    report_type: str | None = Field(None, description="Type confirmed by the reviewer")
    asset_id:    str | None = Field(None, description="Sampled asset the certificate is about")


@app.post("/lab-samples", tags=["Upload"], status_code=201)
def save_lab_sample_endpoint(body: SaveLabSampleRequest,
                             profile: dict = Depends(get_current_user_profile)):
    """Persist a reviewed certificate to lab_samples/lab_results.

    This is the facilities-management save path. The lagoon scope keeps using
    /log and the fixed `readings` table, which the alert engine, dashboards and
    monthly reporting all read; `readings` has fourteen fixed columns and one row
    per site per month, so it cannot hold a certificate with an arbitrary
    parameter list.

    Saving is the human approval step — everything arrives here as `pending` and
    is only recorded because a person confirmed it.
    """
    _ensure_permission(profile, "readings.create",
                       detail="Your role may not save lab reports.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")

    from core.assets import scope_of_asset
    from core.report_types import saves_to_readings
    from db.queries import get_asset, get_or_create_site_id, save_lab_sample

    sample = dict(body.sample or {})
    if not sample.get("report_no"):
        raise HTTPException(status_code=422, detail="report_no is required.")
    if not body.results:
        raise HTTPException(
            status_code=422,
            detail="A certificate with no parameter rows would record that the laboratory "
                   "reported nothing. Nothing was saved.",
        )

    chosen = (body.report_type or sample.get("report_type") or "").strip()

    # Scope comes from the asset the certificate is about — a Legionella count
    # means one thing in a stored tank and another in an open moat. The report
    # type is only consulted for the legacy lagoon path, which predates assets.
    asset = get_asset(body.asset_id, org_id) if body.asset_id else None
    if body.asset_id and not asset:
        raise HTTPException(status_code=404, detail="Unknown asset for this organisation.")
    scope = scope_of_asset(asset)

    if saves_to_readings(chosen, scope):
        raise HTTPException(
            status_code=400,
            detail="Lagoon readings are saved through /api/log so they reach the alert "
                   "engine and monthly reporting.",
        )
    if chosen:
        sample["report_type"] = chosen
    if asset:
        sample["asset_id"] = asset["id"]

    site_id = None
    if body.site:
        site_id = get_or_create_site_id(body.site, org_id, profile.get("token"))

    try:
        sample_id = save_lab_sample(org_id, sample, body.results, site_id=site_id)
    except Exception as exc:
        msg = str(exc)
        if "duplicate key" in msg or "unique" in msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"Report {sample.get('report_no')} has already been saved.",
            )
        raise HTTPException(status_code=500, detail=f"Could not save the certificate: {msg}")
    if not sample_id:
        raise HTTPException(
            status_code=503,
            detail="Lab sample storage is unavailable — migration 016 may not be applied.",
        )

    audit_emit("lab_report.save", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="lab_sample", target_id=str(sample_id),
               report_no=sample.get("report_no"), report_type=sample.get("report_type"),
               parameters=len(body.results))
    return {"sample_id": sample_id, "report_no": sample.get("report_no"),
            "parameters": len(body.results), "message": "Certificate saved."}


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


# ── Corrective actions (Phase 4) ──────────────────────────────────────────────

class CorrectiveActionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    site_id: str | None = None
    severity: str | None = Field(None, description="info/low/medium/high/critical")
    due_date: str | None = Field(None, description="YYYY-MM-DD")
    owner_clerk_id: str | None = Field(None, description="assigned executor")


class CorrectiveActionTransition(BaseModel):
    to_status: str = Field(..., description="in_progress/pending_approval/closed/cancelled")
    note: str | None = None
    evidence_url: str | None = None


@app.get("/actions", tags=["Corrective actions"])
def list_actions(site_id: str | None = None, status: str | None = None,
                 profile: dict = Depends(get_current_user_profile)):
    """List corrective actions in the caller's org (optionally by site/status)."""
    _ensure_permission(profile, "actions.read", detail="Your role cannot view corrective actions.")
    from db.queries import list_corrective_actions
    return {"actions": list_corrective_actions(profile["organization_id"], site_id=site_id, status=status)}


@app.get("/actions/{action_id}", tags=["Corrective actions"])
def get_action(action_id: str, profile: dict = Depends(get_current_user_profile)):
    """A single corrective action with its immutable event history."""
    _ensure_permission(profile, "actions.read", detail="Your role cannot view corrective actions.")
    from db.queries import get_corrective_action, get_corrective_action_events
    action = get_corrective_action(profile["organization_id"], action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    events = get_corrective_action_events(profile["organization_id"], action_id)
    return {"action": action, "events": events}


@app.post("/actions", tags=["Corrective actions"], status_code=201)
def create_action(body: CorrectiveActionCreate, profile: dict = Depends(get_current_user_profile)):
    """Create/assign a corrective action. Managers/Executive assign; the workflow
    then lets the assigned Site Supervisor execute it."""
    _ensure_permission(profile, "actions.create", detail="Your role cannot create corrective actions.")
    from db.queries import create_corrective_action
    action = create_corrective_action(
        profile["organization_id"], body.model_dump(), actor_clerk_id=profile.get("user_id"))
    if not action:
        raise HTTPException(status_code=400, detail="Could not create corrective action.")
    audit_emit("action.create", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="corrective_action", target_id=action["id"])
    return {"action": action}


@app.post("/actions/{action_id}/transition", tags=["Corrective actions"])
def transition_action(action_id: str, body: CorrectiveActionTransition,
                      profile: dict = Depends(get_current_user_profile)):
    """Advance an action through its lifecycle. The target status selects the
    required permission (closure needs actions.close) and the state machine
    rejects illegal transitions — so a Site Supervisor can progress an action but
    only a Manager/Executive can approve closure."""
    from core.corrective import can_transition, required_permission, STATUSES
    from db.queries import get_corrective_action, transition_corrective_action
    if body.to_status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status '{body.to_status}'.")
    action = get_corrective_action(profile["organization_id"], action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Corrective action not found.")
    from_status = action["status"]
    if not can_transition(from_status, body.to_status):
        raise HTTPException(status_code=409,
                            detail=f"Cannot move a '{from_status}' action to '{body.to_status}'.")
    _ensure_permission(profile, required_permission(body.to_status),
                       detail="Your role cannot make this transition.",
                       target_type="corrective_action", target_id=action_id)
    ok, msg = transition_corrective_action(
        profile["organization_id"], action_id, body.to_status, from_status,
        actor_clerk_id=profile.get("user_id"), note=body.note, evidence_url=body.evidence_url)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    audit_emit("action.transition", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="corrective_action", target_id=action_id,
               from_status=from_status, to_status=body.to_status)
    return {"updated": True, "message": msg, "from": from_status, "to": body.to_status}


# ── Inventory & chemical control (Phase 5) ────────────────────────────────────

class InventoryItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    sku: str | None = None
    unit: str | None = None
    reorder_threshold: float | None = None
    unit_cost: float | None = Field(None, description="financial; requires inventory.configure")


class InventoryLocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    kind: str | None = Field(None, description="warehouse/vehicle/site_store")
    site_id: str | None = None


class StockMove(BaseModel):
    item_id: str
    location_id: str
    qty: float = Field(..., gt=0)
    batch_id: str | None = None
    reason: str | None = None
    ref_site_id: str | None = None
    ref_action_id: str | None = None


class StockTransfer(BaseModel):
    item_id: str
    from_location_id: str
    to_location_id: str
    qty: float = Field(..., gt=0)
    batch_id: str | None = None
    reason: str | None = None


class StockAdjust(BaseModel):
    item_id: str
    location_id: str
    qty_delta: float = Field(..., description="signed correction")
    reason: str = Field(..., min_length=1)
    batch_id: str | None = None


# Financial keys stripped from inventory reads unless the caller can see valuation.
_FINANCIAL_ITEM_KEYS = ("unit_cost",)


def _strip_financial(items: list[dict], profile: dict) -> list[dict]:
    # Cost is visible to those who configure it (admins) or view valuation (GM/Exec);
    # operational roles (Site Supervisor) never see cost.
    role = profile.get("role")
    if has_permission(role, "inventory.valuation.read") or has_permission(role, "inventory.configure"):
        return items
    return [{k: v for k, v in it.items() if k not in _FINANCIAL_ITEM_KEYS} for it in items]


@app.get("/inventory/items", tags=["Inventory"])
def inventory_items(profile: dict = Depends(get_current_user_profile)):
    """List stock items. Cost fields are hidden unless the role holds
    inventory.valuation.read (financial-data protection)."""
    _ensure_permission(profile, "inventory.read", detail="Your role cannot view inventory.")
    from db.queries import list_inventory_items
    items = list_inventory_items(profile["organization_id"])
    return {"items": _strip_financial(items, profile)}


@app.post("/inventory/items", tags=["Inventory"], status_code=201)
def create_inventory_item_endpoint(body: InventoryItemCreate,
                                   profile: dict = Depends(get_current_user_profile)):
    """Create an item (master data). unit_cost is a financial field, so this needs
    inventory.configure (operators cannot set costs)."""
    _ensure_permission(profile, "inventory.configure", detail="Your role cannot configure inventory.")
    from db.queries import create_inventory_item
    item = create_inventory_item(profile["organization_id"], body.model_dump())
    if not item:
        raise HTTPException(status_code=400, detail="Could not create item (duplicate SKU?).")
    audit_emit("inventory.item.create", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="inventory_item", target_id=item["id"])
    return {"item": item}


@app.post("/inventory/locations", tags=["Inventory"], status_code=201)
def create_inventory_location_endpoint(body: InventoryLocationCreate,
                                       profile: dict = Depends(get_current_user_profile)):
    _ensure_permission(profile, "inventory.configure", detail="Your role cannot configure inventory.")
    from db.queries import create_inventory_location
    loc = create_inventory_location(profile["organization_id"], body.model_dump())
    if not loc:
        raise HTTPException(status_code=400, detail="Could not create location (duplicate name?).")
    return {"location": loc}


@app.get("/inventory/locations", tags=["Inventory"])
def inventory_locations(profile: dict = Depends(get_current_user_profile)):
    """List storage locations (for stock-movement selectors)."""
    _ensure_permission(profile, "inventory.read", detail="Your role cannot view inventory.")
    from db.queries import list_inventory_locations
    return {"locations": list_inventory_locations(profile["organization_id"])}


@app.get("/inventory/stock", tags=["Inventory"])
def inventory_stock(item_id: str | None = None, profile: dict = Depends(get_current_user_profile)):
    """Current balances per (item, location), computed from the append-only ledger."""
    _ensure_permission(profile, "inventory.read", detail="Your role cannot view inventory.")
    from core.inventory import balance
    from db.queries import get_ledger_rows
    rows = get_ledger_rows(profile["organization_id"], item_id=item_id)
    pairs = {(r["item_id"], r["location_id"]) for r in rows}
    stock = [{
        "item_id": i, "location_id": l, "balance": float(balance(rows, item_id=i, location_id=l)),
    } for (i, l) in sorted(pairs)]
    return {"stock": stock}


@app.post("/inventory/receive", tags=["Inventory"])
def inventory_receive(body: StockMove, profile: dict = Depends(get_current_user_profile)):
    _ensure_permission(profile, "inventory.receive", detail="Your role cannot receive stock.")
    from db.queries import record_receipt
    ok, msg = record_receipt(profile["organization_id"], body.item_id, body.location_id,
                             body.qty, batch_id=body.batch_id, actor_clerk_id=profile.get("user_id"),
                             reason=body.reason)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    audit_emit("inventory.receive", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="inventory_item", target_id=body.item_id, qty=body.qty)
    return {"ok": True, "message": msg}


@app.post("/inventory/consume", tags=["Inventory"])
def inventory_consume(body: StockMove, profile: dict = Depends(get_current_user_profile)):
    """Record chemical usage against an operation. Atomic (RPC) — cannot drive
    stock negative even under concurrent consumes."""
    _ensure_permission(profile, "inventory.consume", detail="Your role cannot record usage.")
    from db.queries import rpc_consume
    ok, msg, bal = rpc_consume(profile["organization_id"], body.item_id, body.location_id, body.qty,
                               batch_id=body.batch_id, actor_clerk_id=profile.get("user_id"),
                               ref_site_id=body.ref_site_id, ref_action_id=body.ref_action_id,
                               reason=body.reason)
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    audit_emit("inventory.consume", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="inventory_item", target_id=body.item_id, qty=body.qty)
    return {"ok": True, "message": msg, "new_balance": bal}


@app.post("/inventory/transfer", tags=["Inventory"])
def inventory_transfer(body: StockTransfer, profile: dict = Depends(get_current_user_profile)):
    _ensure_permission(profile, "inventory.transfer", detail="Your role cannot transfer stock.")
    from db.queries import rpc_transfer
    ok, msg = rpc_transfer(profile["organization_id"], body.item_id, body.from_location_id,
                           body.to_location_id, body.qty, batch_id=body.batch_id,
                           actor_clerk_id=profile.get("user_id"), reason=body.reason)
    if not ok:
        raise HTTPException(status_code=409, detail=msg)
    audit_emit("inventory.transfer", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="inventory_item", target_id=body.item_id, qty=body.qty)
    return {"ok": True, "message": msg}


@app.post("/inventory/adjust", tags=["Inventory"])
def inventory_adjust(body: StockAdjust, profile: dict = Depends(get_current_user_profile)):
    _ensure_permission(profile, "inventory.adjust", detail="Your role cannot adjust stock.")
    from db.queries import record_adjustment
    ok, msg = record_adjustment(profile["organization_id"], body.item_id, body.location_id,
                                body.qty_delta, body.reason, batch_id=body.batch_id,
                                actor_clerk_id=profile.get("user_id"))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    audit_emit("inventory.adjust", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="inventory_item", target_id=body.item_id, qty_delta=body.qty_delta,
               reason=body.reason)
    return {"ok": True, "message": msg}


@app.get("/inventory/valuation", tags=["Inventory"])
def inventory_valuation(profile: dict = Depends(get_current_user_profile)):
    """Organization inventory valuation (GM/Executive KPI). Requires
    inventory.valuation.read — hidden from operational roles."""
    _ensure_permission(profile, "inventory.valuation.read",
                       detail="Your role cannot view inventory valuation.")
    from core.inventory import balance
    from db.queries import get_ledger_rows, list_inventory_items
    items = list_inventory_items(profile["organization_id"])
    rows = get_ledger_rows(profile["organization_id"])
    total = 0.0
    breakdown = []
    for it in items:
        qty = float(balance(rows, item_id=it["id"]))
        cost = float(it.get("unit_cost") or 0)
        value = qty * cost
        total += value
        breakdown.append({"item_id": it["id"], "name": it["name"], "qty": qty,
                          "unit_cost": cost, "value": value})
    return {"total_value": total, "items": breakdown}


# ── Assets & maintenance configuration (Phase 6) ──────────────────────────────

class AssetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    site_id: str | None = None
    asset_type: str | None = Field(None, description="pump/filter/dosing/aerator | water_body/water_tank/fountain/washroom_outlet/misting_line")
    asset_class: str | None = Field(None, description="equipment (maintained) | sampled (a certificate is about it)")
    scope: str | None = Field(None, description="lagoon | facilities — sampled assets only")
    config: dict | None = Field(None, description="checklist, required lab params, thresholds")


class MaintenanceScheduleCreate(BaseModel):
    checklist: dict | None = None
    interval_days: int | None = Field(None, gt=0)
    next_due: str | None = Field(None, description="YYYY-MM-DD")


@app.get("/assets", tags=["Assets"])
def list_assets_endpoint(site_id: str | None = None, asset_class: str | None = None,
                         profile: dict = Depends(get_current_user_profile)):
    """View assets/equipment and their config. All roles with assets.read; General
    Managers see configs read-only, Site Supervisors see what they execute.

    `asset_class=sampled` is what the upload flow asks for: only a sampled asset
    can be the subject of a laboratory certificate.
    """
    _ensure_permission(profile, "assets.read", detail="Your role cannot view assets.")
    from db.queries import list_assets
    return {"assets": list_assets(profile["organization_id"], site_id=site_id,
                                  asset_class=asset_class)}


@app.post("/assets", tags=["Assets"], status_code=201)
def create_asset_endpoint(body: AssetCreate, profile: dict = Depends(get_current_user_profile)):
    """Configure an asset (type, checklist, required lab parameters). Managers/
    Executive only — Site Supervisors execute tasks but don't change templates."""
    _ensure_permission(profile, "assets.configure", detail="Your role cannot configure assets.")
    from core.assets import ASSET_CLASSES, CLASS_SAMPLED, find_type
    from core.report_types import SCOPES
    from db.queries import create_asset, list_asset_types

    custom_types = list_asset_types(profile["organization_id"])
    fields = body.model_dump()

    # Validate the class/type/scope triangle here rather than trusting the client.
    # The database CHECK catches the worst case, but a 422 naming the problem is
    # more use than a constraint violation surfacing as a 400 "could not create".
    if fields.get("asset_class") and fields["asset_class"] not in ASSET_CLASSES:
        raise HTTPException(status_code=422,
                            detail=f"asset_class must be one of {', '.join(ASSET_CLASSES)}.")
    if fields.get("asset_type"):
        t = find_type(fields["asset_type"], custom_types)
        if not t:
            raise HTTPException(status_code=422, detail=f"Unknown asset_type '{fields['asset_type']}'.")
        declared, actual = fields.get("asset_class"), t["asset_class"]
        if declared and declared != actual:
            raise HTTPException(
                status_code=422,
                detail=f"'{fields['asset_type']}' is a {actual} type, not {declared}.",
            )
        fields["asset_class"] = actual          # derive it, so the two cannot disagree
        # A custom type declares its scope; inherit it when the caller did not
        # supply one. Copied by value so editing the type later never re-judges
        # certificates already filed against assets created under it.
        if not fields.get("scope") and t.get("scope"):
            fields["scope"] = t["scope"]
    if fields.get("scope"):
        if fields["scope"] not in SCOPES:
            raise HTTPException(status_code=422, detail=f"scope must be one of {', '.join(SCOPES)}.")
        if fields.get("asset_class") != CLASS_SAMPLED:
            raise HTTPException(
                status_code=422,
                detail="Only a sampled asset carries a specification scope — equipment is "
                       "maintained, never judged against limits.",
            )

    asset = create_asset(profile["organization_id"], fields)
    if not asset:
        raise HTTPException(status_code=400, detail="Could not create asset (duplicate name for site?).")
    audit_emit("asset.configure", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="asset", target_id=asset["id"])
    return {"asset": asset}


class AssetTypeCreate(BaseModel):
    label:       str = Field(..., min_length=1, max_length=80, description="Shown in dropdowns, e.g. 'GRP Tank'")
    asset_class: str = Field(..., description="equipment | sampled")
    scope: str | None = Field(None, description="lagoon | facilities — required for sampled, forbidden for equipment")


@app.get("/asset-types", tags=["Assets"])
def list_asset_types_endpoint(asset_class: str | None = None,
                              profile: dict = Depends(get_current_user_profile)):
    """The asset taxonomy: built-in types plus this organisation's own.

    `asset_class=sampled` is what the upload flow and the certificate paths ask
    for — only a sampled type can be the subject of a laboratory certificate.
    """
    _ensure_permission(profile, "assets.read", detail="Your role cannot view asset types.")
    from core.assets import merge_types
    from db.queries import list_asset_types

    types = merge_types(list_asset_types(profile["organization_id"]))
    if asset_class:
        types = [t for t in types if t["asset_class"] == asset_class]
    return {"types": types}


@app.post("/asset-types", tags=["Assets"], status_code=201)
def create_asset_type_endpoint(body: AssetTypeCreate,
                               profile: dict = Depends(get_current_user_profile)):
    """Add an organisation-defined asset type (Settings → Asset Register).

    A sampled type must declare its scope. A type that cannot say which
    specification set governs it would produce certificates nothing can judge,
    so the requirement is enforced here and again by a database CHECK.
    """
    _ensure_permission(profile, "assets.configure", detail="Only admins can manage the asset register.")
    org_id = profile.get("organization_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with this account.")

    from core.assets import ASSET_CLASSES, CLASS_EQUIPMENT, CLASS_SAMPLED, merge_types
    from core.report_types import SCOPES, normalise_name
    from db.queries import create_asset_type, list_asset_types

    label = normalise_name(body.label)
    if not label:
        raise HTTPException(status_code=422, detail="Asset type name cannot be blank.")
    if body.asset_class not in ASSET_CLASSES:
        raise HTTPException(status_code=422,
                            detail=f"asset_class must be one of {', '.join(ASSET_CLASSES)}.")
    if body.asset_class == CLASS_SAMPLED and body.scope not in SCOPES:
        raise HTTPException(
            status_code=422,
            detail="A sampled asset type must declare a scope (lagoon or facilities) — "
                   "without it, certificates against it cannot be judged.",
        )
    if body.asset_class == CLASS_EQUIPMENT and body.scope:
        raise HTTPException(status_code=422,
                            detail="Equipment is maintained, never judged against limits, so it carries no scope.")

    import re
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if not key:
        raise HTTPException(status_code=422, detail="Asset type name must contain letters or digits.")

    existing = merge_types(list_asset_types(org_id))
    if any(t["key"] == key for t in existing):
        raise HTTPException(status_code=409, detail=f"Asset type '{label}' already exists.")

    try:
        row = create_asset_type(org_id, key, label, body.asset_class,
                                scope=body.scope, created_by=profile.get("user_id"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create asset type: {exc}")
    if not row:
        raise HTTPException(status_code=503,
                            detail="Asset types are unavailable — migration 020 may not be applied.")

    audit_emit("asset_type.create", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=org_id,
               target_type="asset_type", target_id=key,
               asset_class=body.asset_class, scope=body.scope)
    return {"key": key, "label": label, "asset_class": body.asset_class,
            "scope": body.scope, "builtin": False}


@app.delete("/asset-types/{key}", tags=["Assets"])
def delete_asset_type_endpoint(key: str, profile: dict = Depends(get_current_user_profile)):
    """Remove a custom asset type. Built-ins cannot be removed.

    Assets already created under it keep working: they store asset_type,
    asset_class and scope by value, so nothing already filed is re-judged.
    """
    _ensure_permission(profile, "assets.configure", detail="Only admins can manage the asset register.")
    from core.assets import get_asset_type
    from db.queries import delete_asset_type

    if get_asset_type(key):
        raise HTTPException(status_code=400, detail="Built-in asset types cannot be removed.")
    if not delete_asset_type(profile["organization_id"], key):
        raise HTTPException(status_code=500, detail="Could not remove the asset type.")
    audit_emit("asset_type.delete", actor_user_id=profile.get("user_id"),
               actor_role=profile.get("role"), organization_id=profile["organization_id"],
               target_type="asset_type", target_id=key)
    return {"deleted": True, "key": key}


@app.post("/assets/{asset_id}/maintenance", tags=["Assets"], status_code=201)
def create_maintenance_endpoint(asset_id: str, body: MaintenanceScheduleCreate,
                                profile: dict = Depends(get_current_user_profile)):
    """Define a maintenance schedule/checklist for an asset. Managers/Executive."""
    _ensure_permission(profile, "assets.configure", detail="Your role cannot configure maintenance.")
    from db.queries import create_maintenance_schedule
    sched = create_maintenance_schedule(profile["organization_id"], asset_id, body.model_dump())
    if not sched:
        raise HTTPException(status_code=400, detail="Could not create maintenance schedule.")
    return {"schedule": sched}


# ── Management KPI views (Phase 7) ────────────────────────────────────────────

@app.get("/kpi/portfolio", tags=["KPI"])
def kpi_portfolio(profile: dict = Depends(get_current_user_profile)):
    """Portfolio KPIs (General Manager tier and above). Corrective-action health
    and inventory alerts; no financial detail unless the role sees valuation."""
    _ensure_permission(profile, "analytics.portfolio.read",
                       detail="Your role cannot view portfolio KPIs.")
    from db.queries import kpi_summary
    include_fin = has_permission(profile.get("role"), "inventory.valuation.read")
    return {"scope": "portfolio", "kpi": kpi_summary(profile["organization_id"], include_financial=include_fin)}


@app.get("/kpi/executive", tags=["KPI"])
def kpi_executive(profile: dict = Depends(get_current_user_profile)):
    """Organization-wide executive KPIs incl. inventory valuation. Executive only."""
    _ensure_permission(profile, "analytics.executive.read",
                       detail="Your role cannot view executive KPIs.")
    from db.queries import kpi_summary
    return {"scope": "executive", "kpi": kpi_summary(profile["organization_id"], include_financial=True)}


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

