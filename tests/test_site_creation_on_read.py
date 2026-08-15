"""A GET must never bring a site into existence.

L3 of SECURITY_REVIEW_COMPLIANCE.md. Every read helper in db/queries.py resolved
its site through `get_or_create_site_id`, which INSERTs when the name is unknown.
So `GET /readings/{anything}` and `GET /status/{anything}` minted rows in `sites`
for any authenticated caller. The plan/site limit is enforced on POST /sites
alone (api_server.py), so that is a billing control with a query string around
the side of it, and an unbounded row-inflation vector on the tenant's own table.

The regression guard is the row count: these tests assert that no insert on
`sites` is ever issued from a read, not merely that the response looks right.

Two second-order properties are pinned here as well:

  * The read helpers must not fall back to a bare `site_name` filter once
    resolution fails. `readings` and `predictions` carry no organization_id —
    tenancy lives only in site_id — so a name-only filter reads (and, in
    validate_open_predictions, writes) every tenant with a site of that name.
    That is the H1 delete in read form, and it is a fallback the old code could
    barely reach because the site was always created first.
  * A site belonging to ANOTHER organisation must be reported exactly as a site
    that does not exist, wording included — the M3 disclosure decision, applied
    to site names instead of email addresses.

Style follows tests/test_site_deletion_tenancy.py (fake Supabase client, no
network) and tests/test_invite_tenancy.py (endpoint functions called directly
with a fake profile).
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402
import db.queries as queries  # noqa: E402

ORG = "org-alpha"
RIVAL = "org-beta"

KNOWN = "Dubai Safari Lagoon"
UNKNOWN = "Site That Never Existed"
RIVALS_SITE = "Rival Water Feature"

USER = {"user_id": "clerk_user", "role": "admin", "organization_id": ORG,
        "token": "tok"}


# ── fake Supabase ────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, table, store, log):
        self.table, self.store, self.log = table, store, log
        self.filters: dict = {}
        self.op = "select"
        self.payload = None

    def select(self, *a, **k):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def upsert(self, payload, **k):
        self.op, self.payload = "upsert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    # Chainable no-ops — the shapes the helpers use.
    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    @property
    def not_(self):
        return self

    def execute(self):
        self.log.append((self.op, self.table, dict(self.filters)))
        rows = self.store.setdefault(self.table, [])
        if self.op in ("insert", "upsert"):
            row = {"id": f"{self.table}-{len(rows) + 1}", **self.payload}
            rows.append(row)
            return type("R", (), {"data": [row], "count": 1})()
        matched = [r for r in rows
                   if all(r.get(k) == v for k, v in self.filters.items())]
        return type("R", (), {"data": matched, "count": len(matched)})()


class _Client:
    def __init__(self, store, log):
        self.store, self.log = store, log

    def table(self, name):
        return _Q(name, self.store, self.log)


@pytest.fixture
def db(monkeypatch):
    """A world with one site per tenant. Returns (store, log)."""
    store = {
        "sites": [
            {"id": "site-alpha", "organization_id": ORG, "name": KNOWN},
            {"id": "site-beta", "organization_id": RIVAL, "name": RIVALS_SITE},
        ],
        "readings": [],
        "predictions": [],
    }
    log: list[tuple[str, str, dict]] = []
    client = _Client(store, log)
    monkeypatch.setattr(queries, "get_client", lambda *a, **k: client)
    import db.client as db_client
    monkeypatch.setattr(db_client, "get_client", lambda *a, **k: client)
    return store, log


def _site_count(store):
    return len(store["sites"])


# ── the finding ──────────────────────────────────────────────────────────────

READ_HELPERS = [
    ("get_readings_for_site", lambda n: queries.get_readings_for_site(n, organization_id=ORG), []),
    ("reading_exists", lambda n: queries.reading_exists(n, 2026, 3, organization_id=ORG), False),
    ("get_site_reading_count", lambda n: queries.get_site_reading_count(n, organization_id=ORG), 0),
    ("get_validated_predictions", lambda n: queries.get_validated_predictions(n, organization_id=ORG), []),
    ("get_sludge_zones", lambda n: queries.get_sludge_zones(n, organization_id=ORG), []),
    ("get_open_data_requests", lambda n: queries.get_open_data_requests(n, organization_id=ORG), []),
]


@pytest.mark.parametrize("name,call,empty", READ_HELPERS, ids=[h[0] for h in READ_HELPERS])
def test_read_of_an_unknown_site_creates_no_row(db, name, call, empty):
    """The regression guard: the sites table is the same size afterwards."""
    store, log = db
    before = _site_count(store)
    assert call(UNKNOWN) == empty
    assert _site_count(store) == before, (
        f"{name}() inserted a site row for an unknown name — the plan/site "
        "limit is only enforced on POST /sites"
    )
    assert [e for e in log if e[0] in ("insert", "upsert") and e[1] == "sites"] == []


@pytest.mark.parametrize("name,call,empty", READ_HELPERS, ids=[h[0] for h in READ_HELPERS])
def test_read_of_another_tenants_site_creates_no_row_and_returns_nothing(db, name, call, empty):
    store, log = db
    before = _site_count(store)
    assert call(RIVALS_SITE) == empty, f"{name}() read across the tenant boundary"
    assert _site_count(store) == before


@pytest.mark.parametrize("name,call,empty", READ_HELPERS, ids=[h[0] for h in READ_HELPERS])
def test_failed_resolution_does_not_fall_back_to_a_name_filter(db, name, call, empty):
    """`readings`/`predictions` have no organization_id, so a site_name filter
    is cross-tenant by construction."""
    store, log = db
    call(UNKNOWN)
    by_name = [e for e in log if e[1] != "sites" and "site_name" in e[2]]
    assert by_name == [], (
        f"{name}() fell back to a site_name filter: {by_name}. That reads every "
        "tenant with a site of that name."
    )


def test_a_known_site_still_reads_by_site_id(db):
    """The fix must not blind the legitimate case."""
    store, log = db
    store["readings"].append({
        "id": 1, "site_id": "site-alpha", "site_name": KNOWN, "year": 2026,
        "month": 3, "ph": 7.6, "do_mgl": 6.0, "tss_mgl": 10.0,
        "turbidity_ntu": 2.0, "cod_mgl": 20.0, "ammonia_mgl": 0.1,
        "phosphate_mgl": 0.05, "oil_grease_mgl": 0.0, "ecoli_cfu": 0.0,
        "total_coliforms_cfu": 0.0, "chla_ugl": 3.0, "phycocyanin_ugl": 0.5,
        "salinity_psu": 40.0, "water_temp_c": 28.0,
    })
    assert len(queries.get_readings_for_site(KNOWN, organization_id=ORG)) == 1
    assert queries.get_site_reading_count(KNOWN, organization_id=ORG) == 1
    reads = [e for e in log if e[1] == "readings"]
    assert reads and all("site_id" in f for _, _, f in reads)


def test_org_less_callers_keep_the_legacy_name_path(db):
    """agent_server and ui/predictive pass no organization_id. Resolution cannot
    happen at all for them, so the site_name filter must survive — removing it
    would silently empty the single-tenant Streamlit views."""
    store, log = db
    before = _site_count(store)
    queries.get_readings_for_site(UNKNOWN)
    assert _site_count(store) == before
    assert [e for e in log if e[1] == "readings" and "site_name" in e[2]]


# ── the write path is untouched ──────────────────────────────────────────────

def test_the_write_path_still_creates_a_site(db):
    store, _ = db
    before = _site_count(store)
    ok, msg = queries.insert_reading(
        UNKNOWN, 2026, 3, {"ph": 7.4}, organization_id=ORG,
    )
    assert ok, msg
    assert _site_count(store) == before + 1, (
        "ingest must still auto-provision a site; only reads were narrowed"
    )
    assert store["sites"][-1]["name"] == UNKNOWN


def test_deleting_a_zone_for_an_unknown_site_creates_nothing(db):
    """A delete is not a write path that may create — it used to mint the site
    and then report the zone missing."""
    store, _ = db
    before = _site_count(store)
    ok, msg = queries.delete_sludge_zone(UNKNOWN, "Zone A", organization_id=ORG)
    assert not ok
    assert _site_count(store) == before


# ── the HTTP layer ───────────────────────────────────────────────────────────

NOT_FOUND = "Site not found in your organisation."


def _get(fn, site):
    return fn(site, 2026, None, USER)


@pytest.mark.parametrize("endpoint", [api_server.site_readings, api_server.site_status])
def test_get_endpoints_404_on_an_unknown_site(db, endpoint):
    store, log = db
    before = _site_count(store)
    with pytest.raises(HTTPException) as exc:
        _get(endpoint, UNKNOWN)
    assert exc.value.status_code == 404
    assert exc.value.detail == NOT_FOUND
    assert _site_count(store) == before
    assert [e for e in log if e[0] == "insert" and e[1] == "sites"] == []


@pytest.mark.parametrize("endpoint", [api_server.site_readings, api_server.site_status])
def test_another_tenants_site_is_indistinguishable_from_a_missing_one(db, endpoint):
    """Same status, same detail string. A contractor must not be able to probe
    for a competitor's site names one path segment at a time."""
    with pytest.raises(HTTPException) as missing:
        _get(endpoint, UNKNOWN)
    with pytest.raises(HTTPException) as foreign:
        _get(endpoint, RIVALS_SITE)
    assert (missing.value.status_code, missing.value.detail) == \
           (foreign.value.status_code, foreign.value.detail)


@pytest.mark.parametrize("endpoint", [api_server.site_readings, api_server.site_status])
def test_a_real_site_still_answers(db, endpoint):
    body = _get(endpoint, KNOWN)
    assert body["site"] == KNOWN


# ── the control this bypassed ────────────────────────────────────────────────

def test_the_plan_limit_still_fires_on_post_sites(db, monkeypatch):
    """The gate L3 routed around must still be there."""
    monkeypatch.setattr(api_server, "_ensure_permission", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_demo_state", lambda org_id: None)
    import billing
    monkeypatch.setattr(billing, "get_org_billing",
                        lambda org_id: {"site_limit": 1, "plan_name": "starter"})
    monkeypatch.setattr(billing, "count_sites", lambda org_id: 1)

    with pytest.raises(HTTPException) as exc:
        api_server.create_site_endpoint(
            api_server.CreateSiteRequest(name="Second Lagoon"), USER)
    assert exc.value.status_code == 402
    assert "Site limit reached" in exc.value.detail


def test_post_sites_still_creates_under_the_limit(db, monkeypatch):
    store, _ = db
    monkeypatch.setattr(api_server, "_ensure_permission", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_demo_state", lambda org_id: None)
    import billing
    monkeypatch.setattr(billing, "get_org_billing",
                        lambda org_id: {"site_limit": 5, "plan_name": "growth"})
    monkeypatch.setattr(billing, "count_sites", lambda org_id: 1)

    before = _site_count(store)
    body = api_server.create_site_endpoint(
        api_server.CreateSiteRequest(name="Second Lagoon"), USER)
    assert body["name"] == "Second Lagoon"
    assert _site_count(store) == before + 1
