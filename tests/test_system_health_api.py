"""GET /system/health, /system/failures, /system/runs/{run_id} — workflow
observability (031_workflow_events.sql), Layer 2's read side.

The endpoints (api_server.py:3329-3367) already exist and are wired behind
`get_current_user_profile` + `_ensure_permission(profile, "audit.read", ...)`.
What this file tests is the contract underneath them:

    db/queries.py:
        list_workflow_events(organization_id, *, limit=100, since_hours=24,
                              status=None, step=None, entity_id=None, token=None)
        workflow_health_summary(organization_id, *, since_hours=24, token=None)
        list_recent_failures(organization_id, *, limit=50, since_hours=24, token=None)
        get_run(organization_id, run_id, token=None)

As of this file being written, none of the four exist in db/queries.py — the
live-DB tests below will fail loudly (via `_fn`, not a bare AttributeError)
until another agent lands them. That is expected: this file is written to the
CONTRACT, not to today's state, per the task instructions.

WHAT MATTERS, not just coverage:

  1. Tenant isolation, proven positively first — an empty result is not
     evidence of isolation (this codebase has been bitten by exactly that
     twice: see tests/test_rls_clerk_identity.py and
     tests/test_scoped_read_client.py's docstrings).
  2. NULL-organization rows (background jobs — core/workflow.py's
     organization_id defaults to None) must never leak into EITHER tenant.
  3. Tenancy is taken from profile["organization_id"] alone, never a request
     query param or header — the exact CRIT-1 defect fixed at
     api_server.py:388-410 (get_current_user_profile), generalised to these
     three new endpoints.
  4. No token, no data: 401, like every other protected endpoint.
  5. since_hours / limit actually filter, not just accept the arguments.
  6. get_run returns one run's events, in chronological order.
  7. Every distinct reason_code appearing in a /system/health response has an
     entry in that response's `reason_codes` description map.

TWO HALVES, DIFFERENT COSTS, same split as tests/test_rls_clerk_identity.py
and tests/test_scoped_read_client.py:

  * The API half (tenancy-from-profile, 401, reason-code map structure) needs
    no database — it calls the endpoint functions directly with a fake
    profile (tests/test_invite_tenancy.py's style) or drives them over HTTP
    with fastapi.testclient.TestClient for the properties only a real
    dependency chain can prove (401).
  * The live half seeds two throwaway organisations plus NULL-organization
    rows directly into workflow_events via `docker exec supabase-db psql`,
    following tests/test_rls_clerk_identity.py's `_psql` fixture pattern
    exactly, and calls db.queries functions against the real local stack (no
    client patching — service-role scoping is enforced by the `.eq(...)`
    filters these functions must apply, not by RLS, since the backend always
    reads as service_role). SKIPPING IS NOT PASSING: it skips cleanly when
    Docker or the container is absent.

Rows are tagged `zzz-syshealth-<random>-...` in run_id (not just org name) so
teardown can find and delete NULL-organization rows too, which carry no
organisation to key cleanup off of.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402
import db.queries as queries  # noqa: E402
from core.reasons import DESCRIPTIONS  # noqa: E402

CONTAINER = "supabase-db"


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fn(name: str):
    """The named db.queries function, or a hard, clearly-labelled failure.

    Deliberately not a bare `queries.list_workflow_events` reference at import
    time: that would error out EVERY test in the file (a collection failure)
    the instant one function is missing, hiding which ones are actually red.
    """
    got = getattr(queries, name, None)
    if got is None:
        pytest.fail(
            f"db.queries.{name} does not exist yet — the contract in this "
            f"file's docstring is not implemented. RED, not a bug in the test."
        )
    return got


def _profile(role: str = "admin", org: str = "org-mine", token: str | None = None) -> dict:
    return {"user_id": "clerk_x", "role": role, "organization_id": org, "token": token}


@pytest.fixture
def no_demo_gate(monkeypatch):
    """_ensure_permission consults demo state; keep these tests about tenancy,
    not the unrelated demo-expiry gate (matches tests/test_site_creation_on_read.py)."""
    monkeypatch.setattr(api_server, "_demo_state", lambda org_id: None)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Unauthenticated access is refused — needs the REAL dependency chain
# ══════════════════════════════════════════════════════════════════════════════

def test_unauthenticated_requests_are_401d(monkeypatch):
    """No Authorization header at all. Calling the endpoint FUNCTIONS directly
    would skip FastAPI's Depends() resolution entirely and prove nothing — this
    has to go over TestClient so get_current_user_profile's Security(security_jwt)
    dependency actually runs and fails closed (api_server.py:409-410)."""
    monkeypatch.delenv("AUTHZ_FAIL_CLOSED", raising=False)  # default "1" == fail closed
    client = TestClient(api_server.api_app)
    for path in ("/system/health", "/system/failures", "/system/runs/some-run-id"):
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} answered {resp.status_code} with no token"


def test_a_garbage_bearer_token_is_also_401d(monkeypatch):
    monkeypatch.delenv("AUTHZ_FAIL_CLOSED", raising=False)
    client = TestClient(api_server.api_app)
    resp = client.get("/system/health", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 3. Tenancy is never taken from the request (CRIT-1, api_server.py:388-410)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("endpoint,kwargs", [
    (api_server.system_health, {}),
    (api_server.system_failures, {}),
])
def test_endpoint_signatures_carry_no_organization_parameter(endpoint, kwargs):
    """Structural guard: there is no query-string or header parameter these
    endpoints could even read an org id FROM. profile is the only route in."""
    sig = inspect.signature(endpoint)
    for bad in ("organization_id", "org_id", "organization", "x_organization_id"):
        assert bad not in sig.parameters, (
            f"{endpoint.__name__} accepts {bad!r} — tenancy must come only from "
            f"profile['organization_id'], see the CRIT-1 note at api_server.py:388-396"
        )


def test_system_health_scopes_to_the_profiles_org_only(monkeypatch, no_demo_gate):
    seen = []

    def _spy(org_id, *, since_hours=24, token=None):
        seen.append(org_id)
        return {"total": 0}

    monkeypatch.setattr(queries, "workflow_health_summary", _spy)
    api_server.system_health(since_hours=24, profile=_profile(org="org-mine"))
    assert seen == ["org-mine"]


def test_system_failures_scopes_to_the_profiles_org_only(monkeypatch, no_demo_gate):
    seen = []

    def _spy(org_id, *, limit=50, since_hours=24, token=None):
        seen.append(org_id)
        return []

    monkeypatch.setattr(queries, "list_recent_failures", _spy)
    api_server.system_failures(since_hours=24, limit=50, profile=_profile(org="org-mine"))
    assert seen == ["org-mine"]


def test_system_run_scopes_to_the_profiles_org_only(monkeypatch, no_demo_gate):
    seen = []

    def _spy(org_id, run_id, token=None):
        seen.append(org_id)
        return []

    monkeypatch.setattr(queries, "get_run", _spy)
    api_server.system_run(run_id="some-run", profile=_profile(org="org-mine"))
    assert seen == ["org-mine"]


def test_http_layer_a_client_supplied_org_id_is_inert(monkeypatch, no_demo_gate):
    """The end-to-end version of the same property: even when a caller sends an
    organization id as a query param AND a header, pointed at a different
    tenant than their own profile, the query still runs against the profile's
    org. This is precisely the shape of the CRIT-1 IDOR the comment at
    api_server.py:388-410 describes, applied to the new endpoints."""
    seen = []

    def _spy(org_id, *, since_hours=24, token=None):
        seen.append(org_id)
        return {"total": 0}

    monkeypatch.setattr(queries, "workflow_health_summary", _spy)
    api_server.api_app.dependency_overrides[api_server.get_current_user_profile] = (
        lambda: _profile(org="org-mine")
    )
    try:
        client = TestClient(api_server.api_app)
        resp = client.get(
            "/system/health",
            params={"organization_id": "org-rival", "org_id": "org-rival"},
            headers={"X-Organization-Id": "org-rival"},
        )
        assert resp.status_code == 200
    finally:
        api_server.api_app.dependency_overrides.clear()
    assert seen == ["org-mine"], (
        f"a request-supplied organization id changed which tenant was queried: {seen}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. The reason-code map must be complete (structural half)
# ══════════════════════════════════════════════════════════════════════════════

def test_system_health_reason_codes_map_is_the_full_closed_vocabulary(monkeypatch, no_demo_gate):
    """core.reasons.DESCRIPTIONS is the whole closed vocabulary workflow events
    can legally carry a reason_code from (core/workflow.py's step_timer falls
    back to UNEXPECTED_ERROR, never an ad hoc string, when nothing more
    specific applies). So the response's reason_codes map must be at least
    this full set — a narrower map could leave a code the summary actually
    reports with no explanation for the UI."""
    monkeypatch.setattr(queries, "workflow_health_summary", lambda *a, **k: {"total": 0})
    body = api_server.system_health(since_hours=24, profile=_profile())
    assert "reason_codes" in body
    for code, desc in DESCRIPTIONS.items():
        assert code in body["reason_codes"], f"{code} is missing from reason_codes"
        assert body["reason_codes"][code] == desc


def test_system_health_echoes_since_hours(monkeypatch, no_demo_gate):
    monkeypatch.setattr(queries, "workflow_health_summary", lambda *a, **k: {"total": 0})
    body = api_server.system_health(since_hours=48, profile=_profile())
    assert body["since_hours"] == 48


# ══════════════════════════════════════════════════════════════════════════════
# Permission gate sanity — audit.read, not a bespoke check
# ══════════════════════════════════════════════════════════════════════════════

def test_a_role_without_audit_read_is_refused(monkeypatch, no_demo_gate):
    """operator holds no audit.read (core/authz.py's _OPERATOR bundle) — the
    endpoint must 403, not silently answer with someone else's operational data."""
    monkeypatch.setattr(queries, "workflow_health_summary", lambda *a, **k: {"total": 0})
    monkeypatch.setattr(api_server, "audit_denial", lambda *a, **k: None)
    with pytest.raises(HTTPException) as exc:
        api_server.system_health(since_hours=24, profile=_profile(role="operator"))
    assert exc.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# Live half — real Postgres, real workflow_events rows, real db.queries calls
# ══════════════════════════════════════════════════════════════════════════════

def _psql(sql: str) -> str:
    """Run SQL as superuser and return stdout, or skip if the stack is absent.
    Verbatim mechanism from tests/test_rls_clerk_identity.py._psql."""
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    try:
        running = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"docker unavailable: {type(exc).__name__}: {exc}")
    if running.returncode != 0 or CONTAINER not in running.stdout.split():
        pytest.skip(f"no running container named {CONTAINER}")

    proc = subprocess.run(
        ["docker", "exec", "-i", CONTAINER,
         "psql", "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", "-U", "postgres",
         "-d", "postgres"],
        input=sql, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        pytest.fail(f"psql failed:\n{proc.stderr.strip()}\n\nSQL was:\n{sql}")
    return proc.stdout.strip()


def _row(out: str) -> str:
    rows = [line for line in out.splitlines() if line.strip()]
    assert len(rows) == 1, f"expected one result row, got {len(rows)}: {rows}"
    return rows[0]


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return _lit(str(v))


def _insert_events(events: list[dict]) -> None:
    """Insert raw workflow_events rows. Each dict may set:
    run_id (required), org (uuid str or None), step, status, reason_code,
    entity_type, entity_id, duration_ms, hours_ago (age of created_at)."""
    values = []
    for e in events:
        hours_ago = e.get("hours_ago", 0)
        created_at = f"now() - interval '{hours_ago} hours'" if hours_ago else "now()"
        values.append("(%s, %s, %s, %s, %s, %s, %s, %s, %s)" % (
            _lit(e["run_id"]),
            _sql_val(e.get("org")),
            _lit(e.get("step", "ingest")),
            _lit(e.get("status", "ok")),
            _sql_val(e.get("reason_code")),
            _sql_val(e.get("entity_type")),
            _sql_val(e.get("entity_id")),
            _sql_val(e.get("duration_ms")),
            created_at,
        ))
    sql = (
        "BEGIN;\n"
        "INSERT INTO public.workflow_events "
        "(run_id, organization_id, step, status, reason_code, entity_type, entity_id, "
        "duration_ms, created_at)\nVALUES\n" + ",\n".join(values) + ";\nCOMMIT;\n"
    )
    _psql(sql)


@pytest.fixture
def world():
    """Two throwaway organisations. Every seeded row's run_id is prefixed with
    the tag so teardown can find NULL-organization rows too (they carry no
    org to key cleanup off of)."""
    tag = uuid.uuid4().hex[:8]
    prefix = f"zzz-syshealth-{tag}"
    org_a_name = f"{prefix}-mine"
    org_b_name = f"{prefix}-theirs"

    out = _psql(
        "BEGIN;\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(org_a_name)});\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(org_b_name)});\n"
        "COMMIT;\n"
        f"SELECT (SELECT id FROM public.organizations WHERE name = {_lit(org_a_name)})\n"
        f"    || '|' || (SELECT id FROM public.organizations WHERE name = {_lit(org_b_name)});"
    )
    org_a, org_b = _row(out).split("|")

    yield {"org_a": org_a, "org_b": org_b, "prefix": prefix}

    rows_before = _psql(
        f"SELECT count(*) FROM public.workflow_events WHERE run_id LIKE {_lit(prefix + '-%')};"
    )
    _psql(
        "BEGIN;\n"
        f"DELETE FROM public.workflow_events WHERE run_id LIKE {_lit(prefix + '-%')};\n"
        f"DELETE FROM public.organizations WHERE name IN ({_lit(org_a_name)}, {_lit(org_b_name)});\n"
        "COMMIT;\n"
    )
    rows_after = _psql(
        f"SELECT count(*) FROM public.workflow_events WHERE run_id LIKE {_lit(prefix + '-%')};"
    )
    assert rows_after == "0", (
        f"teardown left {rows_after} workflow_events row(s) behind for {prefix} "
        f"(had {rows_before} before delete)"
    )


# ── 1. Tenant isolation, positive first ────────────────────────────────────────

def test_list_workflow_events_shows_the_callers_own_row(world):
    """The positive case FIRST — see this file's docstring and
    tests/test_rls_clerk_identity.py's: an empty result is not evidence of
    isolation."""
    org_a, prefix = world["org_a"], world["prefix"]
    mine = f"{prefix}-mine-positive"
    _insert_events([{"run_id": mine, "org": org_a}])
    rows = _fn("list_workflow_events")(org_a, since_hours=48)
    assert mine in {r["run_id"] for r in rows}, "org A cannot see its own row"


def test_list_workflow_events_excludes_another_tenants_row(world):
    org_a, org_b, prefix = world["org_a"], world["org_b"], world["prefix"]
    mine = f"{prefix}-mine-negative"
    theirs = f"{prefix}-theirs-negative"
    _insert_events([
        {"run_id": mine, "org": org_a},
        {"run_id": theirs, "org": org_b},
    ])
    run_ids = {r["run_id"] for r in _fn("list_workflow_events")(org_a, since_hours=48)}
    assert mine in run_ids, "the positive case must still hold alongside the negative"
    assert theirs not in run_ids, "org A can see org B's workflow_events row"


# ── 2. NULL-organization rows never leak ───────────────────────────────────────

def test_null_organization_rows_are_invisible_to_both_tenants(world):
    org_a, org_b, prefix = world["org_a"], world["org_b"], world["prefix"]
    null_run = f"{prefix}-null-background-job"
    _insert_events([{"run_id": null_run, "org": None}])
    fn = _fn("list_workflow_events")
    a_ids = {r["run_id"] for r in fn(org_a, since_hours=48)}
    b_ids = {r["run_id"] for r in fn(org_b, since_hours=48)}
    assert null_run not in a_ids, "a NULL-organization row leaked into org A's results"
    assert null_run not in b_ids, "a NULL-organization row leaked into org B's results"


# ── 5. since_hours / limit actually filter ─────────────────────────────────────

def test_since_hours_excludes_rows_older_than_the_window(world):
    org_a, prefix = world["org_a"], world["prefix"]
    recent = f"{prefix}-recent"
    old = f"{prefix}-old"
    _insert_events([
        {"run_id": recent, "org": org_a, "hours_ago": 1},
        {"run_id": old, "org": org_a, "hours_ago": 48},
    ])
    fn = _fn("list_workflow_events")
    narrow_ids = {r["run_id"] for r in fn(org_a, since_hours=24)}
    assert recent in narrow_ids
    assert old not in narrow_ids, "since_hours=24 did not exclude a 48h-old row"
    wide_ids = {r["run_id"] for r in fn(org_a, since_hours=72)}
    assert old in wide_ids, "widening the window must bring the old row back"


def test_limit_caps_the_returned_rows(world):
    org_a, prefix = world["org_a"], world["prefix"]
    _insert_events([
        {"run_id": f"{prefix}-limit-{i}", "org": org_a, "hours_ago": 0}
        for i in range(5)
    ])
    rows = _fn("list_workflow_events")(org_a, since_hours=48, limit=2)
    assert len(rows) == 2, f"limit=2 returned {len(rows)} rows"


# ── 6. get_run: one run, chronological order ───────────────────────────────────

def test_get_run_returns_only_that_run_in_chronological_order(world):
    org_a, prefix = world["org_a"], world["prefix"]
    run_id = f"{prefix}-chrono"
    other_run = f"{prefix}-other-run"
    _insert_events([
        {"run_id": run_id, "org": org_a, "step": "obligation", "hours_ago": 0},
        {"run_id": run_id, "org": org_a, "step": "ingest", "hours_ago": 3},
        {"run_id": run_id, "org": org_a, "step": "parse", "hours_ago": 2},
        {"run_id": other_run, "org": org_a, "step": "ingest", "hours_ago": 1},
    ])
    events = _fn("get_run")(org_a, run_id)
    assert all(e["run_id"] == run_id for e in events), "get_run returned another run's events"
    steps = [e["step"] for e in events]
    assert steps == ["ingest", "parse", "obligation"], (
        f"events are not in chronological (oldest-first) order: {steps}"
    )


def test_get_run_does_not_cross_the_tenant_boundary(world):
    """Same run_id shape, but the run belongs to org B. Org A must get nothing —
    api_server.py's docstring for /system/runs/{run_id} promises this never
    reveals whether a run_id exists outside the caller's tenant."""
    org_a, org_b, prefix = world["org_a"], world["org_b"], world["prefix"]
    run_id = f"{prefix}-cross-tenant-run"
    _insert_events([{"run_id": run_id, "org": org_b, "step": "ingest"}])
    events = _fn("get_run")(org_a, run_id)
    assert events == [], "org A retrieved a run belonging to org B"


# ── list_recent_failures: scoping + status ─────────────────────────────────────

def test_list_recent_failures_shows_only_the_callers_failures(world):
    org_a, org_b, prefix = world["org_a"], world["org_b"], world["prefix"]
    mine_fail = f"{prefix}-fail-mine"
    mine_ok = f"{prefix}-ok-mine"
    theirs_fail = f"{prefix}-fail-theirs"
    null_fail = f"{prefix}-fail-null"
    _insert_events([
        {"run_id": mine_fail, "org": org_a, "status": "failed", "reason_code": "DB_ERROR"},
        {"run_id": mine_ok, "org": org_a, "status": "ok"},
        {"run_id": theirs_fail, "org": org_b, "status": "failed", "reason_code": "DB_ERROR"},
        {"run_id": null_fail, "org": None, "status": "failed", "reason_code": "DB_ERROR"},
    ])
    rows = _fn("list_recent_failures")(org_a, since_hours=48)
    run_ids = {r["run_id"] for r in rows}
    assert mine_fail in run_ids, "org A cannot see its own failure (positive case)"
    assert theirs_fail not in run_ids, "org A can see org B's failure"
    assert null_fail not in run_ids, "a NULL-organization failure leaked to org A"
    assert mine_ok not in run_ids, "list_recent_failures returned a non-failed row"


def test_list_recent_failures_limit_caps_the_result(world):
    org_a, prefix = world["org_a"], world["prefix"]
    _insert_events([
        {"run_id": f"{prefix}-fail-limit-{i}", "org": org_a, "status": "failed",
         "reason_code": "DB_ERROR"}
        for i in range(4)
    ])
    rows = _fn("list_recent_failures")(org_a, since_hours=48, limit=2)
    assert len(rows) == 2


# ── 7. reason_codes map completeness against REAL seeded reason codes ─────────

def test_reason_codes_seen_in_a_real_summary_are_all_explained(world, monkeypatch, no_demo_gate):
    """The end-to-end version of the structural test above: seed real rows
    carrying real core.reasons codes for the caller's own org, call the actual
    workflow_health_summary against the live DB, wrap it in the real
    system_health endpoint, and confirm every code that round-trips through
    the summary is present (and correctly described) in reason_codes."""
    org_a, prefix = world["org_a"], world["prefix"]
    seeded_codes = ["DB_ERROR", "SITE_UNRESOLVED"]
    _insert_events([
        {"run_id": f"{prefix}-reason-{code}", "org": org_a, "status": "failed",
         "reason_code": code}
        for code in seeded_codes
    ])
    summary_fn = _fn("workflow_health_summary")
    summary = summary_fn(org_a, since_hours=48)
    # system_health does its own `from db.queries import workflow_health_summary`
    # internally and re-runs the same live query — calling it directly exercises
    # the exact path the HTTP endpoint does, not a mock of it.
    body = api_server.system_health(since_hours=48, profile=_profile(org=org_a))

    blob = json.dumps(summary, default=str)
    for code in seeded_codes:
        assert code in blob, (
            f"{code} was seeded into workflow_events for this org but does not "
            f"appear anywhere in workflow_health_summary's output: {summary}"
        )
        assert code in body["reason_codes"], f"{code} appears in the summary but has no explanation"
        assert body["reason_codes"][code] == DESCRIPTIONS[code]
