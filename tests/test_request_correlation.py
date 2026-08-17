"""Per-request correlation id: contextvar isolation, middleware round-trip, audit stamping.

core/observability.py claims a contextvars-based request id specifically because
this server is ASGI and multiplexes many concurrent requests onto one thread —
a plain module global or a threading.local would let one request's id leak into
another's audit trail. That claim is not free: it is trivially easy to "fix" a
bug by reaching for a global and have every single-request test still pass. So
the first test here runs several concurrent asyncio tasks, each setting its own
id, and asserts none ever observes another's — a global or thread-local
implementation MUST fail it.

The rest of the file proves the request id actually reaches the two places that
matter: the response header (round-tripped through a real Starlette app via
TestClient, not the live server) and the audit event's `context` JSONB (audit_events
has no request_id column, per core/audit.py's docstring, so it must ride inside
`context` rather than as a top-level field that would break the insert).

Style follows tests/test_scope_resolution_failure.py: monkeypatched seams, no
network, no database.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.audit as audit  # noqa: E402
from core.observability import (  # noqa: E402
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    current_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)


# ── 1. contextvar isolation under concurrency ─────────────────────────────────

async def _run_and_observe(rid: str, barrier: asyncio.Barrier, results: dict) -> None:
    """Set `rid` as the current request id, wait for every sibling task to have
    set its own, then record what this task observes. If the implementation
    were a global or thread-local, the barrier forces the interleaving that
    would expose it: every task would observe the last id set, not its own.
    """
    token = set_request_id(rid)
    try:
        await barrier.wait()
        # Yield control again so other tasks can run between our set and our read.
        await asyncio.sleep(0)
        results[rid] = current_request_id()
    finally:
        reset_request_id(token)


async def _concurrency_scenario(n: int) -> dict:
    barrier = asyncio.Barrier(n)
    ids = [f"rid-{i}" for i in range(n)]
    results: dict = {}
    await asyncio.gather(*(_run_and_observe(rid, barrier, results) for rid in ids))
    return results


def test_contextvar_isolates_ids_across_concurrent_tasks():
    results = asyncio.run(_concurrency_scenario(8))
    assert len(results) == 8
    for rid, observed in results.items():
        assert observed == rid, (
            f"task set {rid!r} but observed {observed!r} — the request id "
            "leaked across concurrent tasks; this implementation is not "
            "actually per-request (global or thread-local?)."
        )


def test_current_request_id_is_none_outside_any_request():
    # No middleware, no set_request_id call — a script or a test that never
    # went through the middleware must see None, not a stale value from a
    # different test. (If this fails, some other test forgot to reset.)
    assert current_request_id() is None


def test_new_request_id_generates_distinct_values():
    ids = {new_request_id() for _ in range(50)}
    assert len(ids) == 50


# ── 2. round-trip through the middleware ──────────────────────────────────────

def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    def echo():
        return {"request_id": current_request_id()}

    return app


def test_inbound_request_id_is_echoed():
    client = TestClient(_build_app())
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: "caller-supplied-123"})
    assert resp.status_code == 200
    assert resp.headers[REQUEST_ID_HEADER] == "caller-supplied-123"
    assert resp.json()["request_id"] == "caller-supplied-123"


def test_absent_request_id_is_generated():
    client = TestClient(_build_app())
    resp = client.get("/echo")
    assert resp.status_code == 200
    generated = resp.headers.get(REQUEST_ID_HEADER)
    assert generated, "middleware must always set the response header"
    assert resp.json()["request_id"] == generated


def test_response_header_present_even_when_handler_raises():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/boom")
    def boom():
        raise RuntimeError("handler exploded")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert REQUEST_ID_HEADER in resp.headers, (
        "the request id header must be set on the response regardless of "
        "whether the handler succeeded, raised, or was denied"
    )


def test_two_sequential_requests_get_different_generated_ids():
    client = TestClient(_build_app())
    first = client.get("/echo").headers[REQUEST_ID_HEADER]
    second = client.get("/echo").headers[REQUEST_ID_HEADER]
    assert first != second


# ── 3. audit stamps the request id into `context`, not as a top-level column ──

class _RecordingClient:
    """A fake Supabase client that records what gets inserted into a table."""

    def __init__(self):
        self.inserted_rows = []

    def table(self, name):
        assert name == "audit_events"
        return self

    def insert(self, row):
        self.inserted_rows.append(row)
        return self

    def execute(self):
        return None


def test_emit_stamps_current_request_id_into_context(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    token = set_request_id("rid-for-audit-test")
    try:
        audit.emit(
            "site.delete",
            actor_user_id="user_1",
            actor_role="admin",
            organization_id="org_1",
            target_type="site",
            target_id="site_9",
        )
    finally:
        reset_request_id(token)

    assert recorder.inserted_rows, "emit() must call _persist, which must insert a row"
    row = recorder.inserted_rows[0]

    # audit_events has NO request_id column — asserting its absence as a
    # top-level key is a positive fact about the schema contract, not just
    # tidiness: a top-level request_id would break the insert against the
    # real table.
    assert "request_id" not in row

    context = row.get("context") or {}
    assert context.get("request_id") == "rid-for-audit-test", (
        "the current request id must be stamped into the `context` JSONB "
        "column; got context=%r" % (context,)
    )


def test_emit_without_a_current_request_id_does_not_add_one(monkeypatch):
    """Outside any request (a script, a background job), context must not
    claim a request id that doesn't exist."""
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    assert current_request_id() is None
    audit.emit(
        "role.assign",
        actor_user_id="user_1",
        actor_role="admin",
        organization_id="org_1",
    )

    assert recorder.inserted_rows
    context = recorder.inserted_rows[0].get("context") or {}
    assert "request_id" not in context or context.get("request_id") is None


# ── 4. auditing never breaks the request ──────────────────────────────────────

def test_emit_never_raises_even_when_persist_is_broken(monkeypatch):
    """core/audit.py's docstring: 'It must NEVER raise into a request path.'
    Force the DB layer underneath _persist to blow up and assert emit()
    still returns normally.
    """

    def _boom(*a, **k):
        raise RuntimeError("db connection reset by peer")

    monkeypatch.setattr("db.client.get_client", _boom)

    # Must not raise.
    audit.emit(
        "site.delete",
        actor_user_id="user_1",
        actor_role="admin",
        organization_id="org_1",
        target_type="site",
        target_id="site_9",
    )


def test_emit_never_raises_when_table_insert_itself_fails(monkeypatch):
    class _BoomOnInsert:
        def table(self, name):
            return self

        def insert(self, row):
            raise RuntimeError("relation \"audit_events\" does not exist")

        def execute(self):
            return None

    monkeypatch.setattr("db.client.get_client", lambda *a, **k: _BoomOnInsert())

    audit.emit(
        "report.finalize",
        actor_user_id="user_1",
        actor_role="admin",
        organization_id="org_1",
    )
