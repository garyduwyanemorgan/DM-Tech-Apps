"""The scoped read client is what gives the dormant RLS work any value at all.

029/030 wrote and re-keyed the policies; test_rls_clerk_identity.py proves the
policies themselves discriminate correctly when Postgres evaluates them as the
`authenticated` role. But every one of those tests runs the query as service_role
would never run it in production — the app's reads all went through
`db.client.get_client()` with no token, which is the service_role singleton and
bypasses RLS entirely. Row-level security enforced only in a psql shell is a
demo, not a control.

This file is the missing link: it proves (a) the nine read functions in
db/queries.py actually forward a caller's token into the client they build,
rather than silently reusing service_role, and (b) `db.client.get_client(token)`
fails CLOSED — never service_role — when the anon key it requires is not
configured. Together those two properties are what make "RLS is enforced for
per-user reads" a true sentence about this codebase rather than an aspiration
about the schema.

TWO HALVES, DIFFERENT COSTS, same split as test_rls_clerk_identity.py:

  * The static/unit half needs no database. It patches `get_client` with a
    recorder and asserts each function called it WITH the token it was given.
    This is a regression guard: the token is a keyword-default parameter on
    every one of these functions, so a future edit can drop `token` from a
    `get_client(...)` call and every existing test still passes — nothing else
    notices a silently-dropped token, because the fallback (service_role) still
    answers the query, just without RLS. That is precisely the bug this file
    exists to catch.

  * The live half proves the positive first, exactly as test_rls_clerk_identity
    insists: an empty result set is not evidence of tenancy. It creates two
    organisations, a site with a reading in each, and one Clerk-identified user
    in the first — then runs the SAME queries select_sites/select_readings
    enforce (029_rls_tenant_scope.sql) as the `authenticated` role with that
    user's claim set, via `docker exec psql`, following
    test_rls_clerk_identity.py's `_as_clerk_user` mechanism exactly. That
    mechanism reproduces what PostgREST does per request (SET LOCAL
    request.jwt.claims inside a transaction) without needing a genuine
    Clerk-signed RS256 token, which this suite cannot mint — Clerk holds the
    private key. It is the same substitution test_rls_clerk_identity.py makes,
    applied to the tables get_readings_for_site/get_site_names actually query.

SKIPPING IS NOT PASSING. The live half skips when Docker or the container is
absent. A skip means THIS WAS NOT EXERCISED — see `_psql` below, verbatim from
test_rls_clerk_identity.py.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db.client as db_client  # noqa: E402
import db.queries as queries  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# Static/unit half — no database
# ══════════════════════════════════════════════════════════════════════════════


class _Result:
    def __init__(self, data=None, count=0):
        self.data = data if data is not None else []
        self.count = count


class _ChainStub:
    """A postgrest-shaped query chain. Every filter/order/select call returns
    self so any chain the query functions build succeeds; `.execute()` always
    reports zero rows, so functions take their empty-result path rather than
    trying to parse fabricated data."""

    def execute(self):
        return _Result()

    def __getattr__(self, _name):
        return lambda *a, **kw: self


class _RecordingClient:
    """Stands in for the client `get_client()` would return. Its own presence
    is not what's under test here — the ARGUMENT it was built with is."""

    def table(self, _name):
        return _ChainStub()


class _Recorder:
    """Records every token `get_client` was called with, then hands back a
    working stub client so the function under test can run to completion."""

    def __init__(self):
        self.calls: list[str | None] = []
        self._client = _RecordingClient()

    def __call__(self, token: str | None = None):
        self.calls.append(token)
        return self._client


@pytest.fixture
def recorder(monkeypatch):
    """Patch get_client in BOTH bindings.

    db/queries.py does `from .client import get_client`, which binds the name
    into the queries module at import time. Patching db.client.get_client alone
    leaves db.queries still holding the original function, so the call goes
    straight to the live stack (or silently no-ops if unconfigured) and the
    test passes for the wrong reason — exactly the trap
    test_scope_resolution_failure.py's `_patch_client` documents.
    """
    rec = _Recorder()
    monkeypatch.setattr(queries, "get_client", rec)
    monkeypatch.setattr(db_client, "get_client", rec)
    return rec


TOKEN = "user.jwt.token-abc123"


def test_get_readings_for_site_forwards_token(recorder):
    queries.get_readings_for_site("Site A", organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_get_site_names_forwards_token(recorder):
    queries.get_site_names(organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_reading_exists_forwards_token(recorder):
    queries.reading_exists("Site A", 2026, 1, organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_get_validated_predictions_forwards_token(recorder):
    queries.get_validated_predictions(site_name=None, organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_get_site_reading_count_forwards_token(recorder):
    queries.get_site_reading_count("Site A", organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_get_sludge_zones_forwards_token(recorder):
    queries.get_sludge_zones("Site A", organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_get_open_data_requests_forwards_token(recorder):
    queries.get_open_data_requests("Site A", organization_id=None, token=TOKEN)
    assert TOKEN in recorder.calls


def test_read_site_id_forwards_token(recorder):
    """organization_id must be truthy here — with none, _read_site_id short-
    circuits to (None, True) without ever consulting the client, which would
    make this test vacuous."""
    queries._read_site_id("Site A", "org_1", TOKEN)
    assert TOKEN in recorder.calls


def test_find_site_id_forwards_token(recorder):
    queries.find_site_id("Site A", "org_1", TOKEN)
    assert TOKEN in recorder.calls


# ── Fail-closed: no anon key configured ────────────────────────────────────────

def test_get_client_with_token_fails_closed_when_anon_key_missing(monkeypatch):
    """The single most important assertion in this file.

    Service-role credentials ARE configured (as they would be in production);
    only the anon key is missing. A caller that forgets to set
    SUPABASE_ANON_KEY must get NO client back for a token-scoped request — never
    a client silently rebuilt from service_role, which would bypass RLS exactly
    as if no scoping had been requested at all.
    """
    sentinel_service_client = object()
    monkeypatch.setattr(db_client, "_secrets",
                         lambda: {"url": "https://example.supabase.co", "key": "service-role-key"})
    monkeypatch.setattr(db_client, "_anon_secrets", lambda: None)
    monkeypatch.setattr(db_client, "create_client", lambda *a, **k: sentinel_service_client)
    monkeypatch.setattr(db_client, "_client", None)

    result = db_client.get_client("some.token")

    assert result is None
    assert result is not sentinel_service_client


def test_get_client_with_token_does_not_reuse_the_service_role_singleton(monkeypatch):
    """Even when a service_role singleton already exists in memory, a
    token-scoped call without an anon key must not hand it out."""
    sentinel_service_client = object()
    monkeypatch.setattr(db_client, "_secrets",
                         lambda: {"url": "https://example.supabase.co", "key": "service-role-key"})
    monkeypatch.setattr(db_client, "_anon_secrets", lambda: None)
    monkeypatch.setattr(db_client, "_client", sentinel_service_client)

    assert db_client.get_client("some.token") is None
    assert db_client.get_client("some.token") is not sentinel_service_client


# ── Unchanged behaviour: no-token path is still the service_role singleton ────

def test_get_client_no_token_still_returns_service_role_singleton(monkeypatch):
    calls = {"n": 0}

    def _fake_create_client(_url, _key):
        calls["n"] += 1
        return object()

    monkeypatch.setattr(db_client, "_secrets",
                         lambda: {"url": "https://example.supabase.co", "key": "service-role-key"})
    monkeypatch.setattr(db_client, "create_client", _fake_create_client)
    monkeypatch.setattr(db_client, "_client", None)

    first = db_client.get_client()
    second = db_client.get_client()

    assert first is not None
    assert first is second, "get_client() must keep returning the SAME singleton"
    assert calls["n"] == 1, "a second no-token call must not rebuild the client"


def test_get_client_no_token_does_not_consult_anon_secrets(monkeypatch):
    """The unchanged path must still resolve through the service_role secrets,
    not accidentally start reading the anon key."""
    monkeypatch.setattr(db_client, "_secrets",
                         lambda: {"url": "https://example.supabase.co", "key": "service-role-key"})
    monkeypatch.setattr(db_client, "create_client", lambda *a, **k: object())
    monkeypatch.setattr(db_client, "_client", None)

    def _boom():
        raise AssertionError("get_client() with no token must not call _anon_secrets")

    monkeypatch.setattr(db_client, "_anon_secrets", _boom)
    assert db_client.get_client() is not None


# ══════════════════════════════════════════════════════════════════════════════
# Live half — real Postgres, real RLS policies, real JWT claims
# ══════════════════════════════════════════════════════════════════════════════
#
# Mechanism copied verbatim from tests/test_rls_clerk_identity.py: SET LOCAL
# request.jwt.claims inside a transaction, run as the `authenticated` role,
# via `docker exec psql`. This reproduces what PostgREST does per request and
# is what actually backs `db.client.get_client(token).postgrest.auth(token)` —
# a genuine Clerk-signed token cannot be minted in-process (Clerk holds the
# private key), so this is the same substitution the existing suite makes.

CONTAINER = "supabase-db"


def _psql(sql: str) -> str:
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


def _as_clerk_user(subject: str | None, query: str) -> str:
    if subject is None:
        claim = ""
    else:
        claims = json.dumps({"sub": subject, "role": "authenticated"})
        claim = "SET LOCAL request.jwt.claims = %s;" % _lit(claims)
    return _psql(
        "BEGIN;\n"
        "SET LOCAL ROLE authenticated;\n"
        f"{claim}\n"
        f"{query}\n"
        "ROLLBACK;\n"
    )


@pytest.fixture(scope="module")
def scoped_tenant():
    """Two organisations, each with one site and one reading; one Clerk user
    profile in the first organisation. Removed in teardown."""
    tag = uuid.uuid4().hex[:8]
    mine = f"zzz-scoped-read-mine-{tag}"
    theirs = f"zzz-scoped-read-theirs-{tag}"
    subject = f"user_zzzread{tag}"

    out = _psql(
        "BEGIN;\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(mine)});\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(theirs)});\n"
        "INSERT INTO public.user_profiles (id, organization_id, role, clerk_id, email)\n"
        "VALUES (gen_random_uuid(),\n"
        f"        (SELECT id FROM public.organizations WHERE name = {_lit(mine)}),\n"
        f"        'admin', {_lit(subject)}, {_lit(subject + '@example.test')});\n"
        "INSERT INTO public.sites (id, organization_id, name, volume_m3, salinity_baseline)\n"
        "VALUES (gen_random_uuid(),\n"
        f"        (SELECT id FROM public.organizations WHERE name = {_lit(mine)}),\n"
        f"        {_lit('Zzz Mine Site ' + tag)}, 100, 45);\n"
        "INSERT INTO public.sites (id, organization_id, name, volume_m3, salinity_baseline)\n"
        "VALUES (gen_random_uuid(),\n"
        f"        (SELECT id FROM public.organizations WHERE name = {_lit(theirs)}),\n"
        f"        {_lit('Zzz Theirs Site ' + tag)}, 100, 45);\n"
        "INSERT INTO public.readings (site_id, site_name, year, month, ph)\n"
        "VALUES ((SELECT id FROM public.sites WHERE name = "
        f"{_lit('Zzz Mine Site ' + tag)}), {_lit('Zzz Mine Site ' + tag)}, 2026, 1, 7.5);\n"
        "INSERT INTO public.readings (site_id, site_name, year, month, ph)\n"
        "VALUES ((SELECT id FROM public.sites WHERE name = "
        f"{_lit('Zzz Theirs Site ' + tag)}), {_lit('Zzz Theirs Site ' + tag)}, 2026, 1, 7.5);\n"
        "COMMIT;\n"
        f"SELECT (SELECT id FROM public.organizations WHERE name = {_lit(mine)})\n"
        f"    || '|' || (SELECT id FROM public.sites WHERE name = {_lit('Zzz Mine Site ' + tag)})\n"
        f"    || '|' || (SELECT id FROM public.sites WHERE name = {_lit('Zzz Theirs Site ' + tag)});"
    )
    org_id, mine_site_id, theirs_site_id = _row(out).split("|")

    yield {
        "subject": subject,
        "org_id": org_id,
        "mine_site_id": mine_site_id,
        "theirs_site_id": theirs_site_id,
        "mine_site_name": f"Zzz Mine Site {tag}",
        "theirs_site_name": f"Zzz Theirs Site {tag}",
    }

    _psql(
        "BEGIN;\n"
        f"DELETE FROM public.readings WHERE site_id IN ({_lit(mine_site_id)}, {_lit(theirs_site_id)});\n"
        f"DELETE FROM public.sites WHERE id IN ({_lit(mine_site_id)}, {_lit(theirs_site_id)});\n"
        f"DELETE FROM public.user_profiles WHERE clerk_id = {_lit(subject)};\n"
        "DELETE FROM public.organizations WHERE name IN "
        f"({_lit(mine)}, {_lit(theirs)});\n"
        "COMMIT;\n"
    )


def test_scoped_caller_sees_their_own_site(scoped_tenant):
    """The positive case, first — an empty result set is not evidence of
    tenancy. Proves select_sites (029_rls_tenant_scope.sql) actually admits the
    row belonging to the caller's own organisation under a live per-user claim
    set, which is the policy get_site_names()/get_or_create_site_id() rely on
    once their client is built from a token instead of service_role."""
    got = _as_clerk_user(
        scoped_tenant["subject"],
        "SELECT count(*) FROM public.sites WHERE id = %s;" % _lit(scoped_tenant["mine_site_id"]),
    )
    assert _row(got) == "1", "the caller cannot see their own site"


def test_scoped_caller_cannot_see_the_other_tenants_site(scoped_tenant):
    """Only after the positive is established does the negative mean anything."""
    got = _as_clerk_user(
        scoped_tenant["subject"],
        "SELECT count(*) FROM public.sites WHERE id = %s;" % _lit(scoped_tenant["theirs_site_id"]),
    )
    assert _row(got) == "0", "the caller can see another tenant's site"


def test_scoped_caller_sees_their_own_reading_and_only_it(scoped_tenant):
    """select_readings walks through sites.organization_id, so this exercises
    the join get_readings_for_site's query would traverse under a real token."""
    got = _as_clerk_user(
        scoped_tenant["subject"],
        "SELECT count(*) FILTER (WHERE site_id = %s) || '|' || count(*)\n"
        "  FROM public.readings;" % _lit(scoped_tenant["mine_site_id"]),
    )
    mine, total = _row(got).split("|")
    assert mine == "1", "the caller cannot see their own reading"
    assert total == "1", "the caller can see another tenant's reading"


def test_no_claim_at_all_sees_no_sites(scoped_tenant):
    """The fail-closed direction: a caller with no subject (the state of a
    request whose token never got forwarded — the exact bug the unit half
    above guards against) sees nothing, not everything."""
    got = _as_clerk_user(
        None,
        "SELECT count(*) FROM public.sites WHERE id IN (%s, %s);"
        % (_lit(scoped_tenant["mine_site_id"]), _lit(scoped_tenant["theirs_site_id"])),
    )
    assert _row(got) == "0"
