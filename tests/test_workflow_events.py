"""core/workflow.py: per-step compliance-pipeline event recording (Layer 2).

The differentiating question this module exists to answer is not "did the
server 500" but "why is Site 7's March obligation still non-compliant" — which
pipeline step (ingest/parse/validate/persist/assess/obligation/report) it
stalled at, and why. Two properties matter more than coverage:

  1. `step_timer` must re-raise the caller's exception (it records outcomes,
     it does not swallow them) while still emitting a "failed" event with a
     reason code.
  2. `emit_step` (and therefore `step_timer`) must never raise into the
     caller, even when the DB layer underneath `_persist` is completely
     broken — recording a workflow outcome must not itself become a new
     failure mode, mirroring core/audit.py's hard rule.

Persistence follows the exact same seam as core/audit.py: `db.client.get_client()`
is imported lazily inside `_persist` and called with no args, then
`.table("workflow_events").insert(row).execute()`. Patching only a reference to
`db.client.get_client` elsewhere would miss the name bound inside
core/workflow.py's own `_persist` — see tests/test_scope_resolution_failure.py's
`_patch_client` note; here it is enough to patch `db.client.get_client` because
`_persist` does its `from db.client import get_client` fresh on every call
(confirmed by reading core/workflow.py) rather than binding it at module import
time.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.workflow as workflow  # noqa: E402
from core.observability import reset_request_id, set_request_id  # noqa: E402


class _RecordingClient:
    """A fake Supabase client that records what gets inserted into a table."""

    def __init__(self):
        self.inserted_rows = []

    def table(self, name):
        assert name == "workflow_events"
        return self

    def insert(self, row):
        self.inserted_rows.append(row)
        return self

    def execute(self):
        return None


class _BoomClient:
    """A client whose every call raises, simulating a fully broken DB layer."""

    def table(self, _name):
        raise RuntimeError("connection reset by peer")


# ── step constants ─────────────────────────────────────────────────────────────

def test_step_constants_are_the_canonical_pipeline_names():
    assert workflow.INGEST == "ingest"
    assert workflow.PARSE == "parse"
    assert workflow.VALIDATE == "validate"
    assert workflow.PERSIST == "persist"
    assert workflow.ASSESS == "assess"
    assert workflow.OBLIGATION == "obligation"
    assert workflow.REPORT == "report"


def test_new_run_id_generates_distinct_values():
    ids = {workflow.new_run_id() for _ in range(20)}
    assert len(ids) == 20


# ── emit_step: content and never-raises ─────────────────────────────────────────

def test_emit_step_persists_expected_fields(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    run_id = workflow.new_run_id()
    workflow.emit_step(
        workflow.PARSE,
        status="ok",
        run_id=run_id,
        organization_id="org_1",
        entity_type="lab_sample",
        entity_id="sample_9",
        duration_ms=42,
        extra_field="value",
    )

    assert recorder.inserted_rows, "emit_step must persist a row"
    row = recorder.inserted_rows[0]
    assert row["run_id"] == run_id
    assert row["step"] == workflow.PARSE
    assert row["status"] == "ok"
    assert row["organization_id"] == "org_1"
    assert row["entity_type"] == "lab_sample"
    assert row["entity_id"] == "sample_9"
    assert row["duration_ms"] == 42
    assert (row.get("context") or {}).get("extra_field") == "value"


def test_emit_step_stamps_the_current_request_id(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    token = set_request_id("rid-workflow-test")
    try:
        workflow.emit_step(
            workflow.INGEST,
            status="ok",
            run_id=workflow.new_run_id(),
        )
    finally:
        reset_request_id(token)

    assert recorder.inserted_rows
    assert recorder.inserted_rows[0]["request_id"] == "rid-workflow-test"


def test_emit_step_never_raises_when_db_layer_is_broken(monkeypatch):
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    # Must not raise.
    workflow.emit_step(workflow.INGEST, status="ok", run_id=workflow.new_run_id())


def test_emit_step_never_raises_when_insert_itself_fails(monkeypatch):
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: _BoomClient())
    # Must not raise.
    workflow.emit_step(workflow.VALIDATE, status="failed", run_id=workflow.new_run_id(), reason_code="DB_ERROR")


def test_emit_step_never_raises_with_no_client_configured(monkeypatch):
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: None)
    workflow.emit_step(workflow.PERSIST, status="ok", run_id=workflow.new_run_id())


# ── step_timer: ok on success, failed + re-raise on exception ──────────────────

def test_step_timer_emits_ok_on_success(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    run_id = workflow.new_run_id()
    with workflow.step_timer(workflow.ASSESS, run_id=run_id, organization_id="org_1"):
        pass  # normal completion

    assert len(recorder.inserted_rows) == 1
    row = recorder.inserted_rows[0]
    assert row["status"] == "ok"
    assert row["step"] == workflow.ASSESS
    assert row["duration_ms"] is not None
    assert row["duration_ms"] >= 0


def test_step_timer_reraises_the_original_exception(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    class _CustomError(Exception):
        pass

    run_id = workflow.new_run_id()
    with pytest.raises(_CustomError, match="pipeline blew up"):
        with workflow.step_timer(workflow.OBLIGATION, run_id=run_id):
            raise _CustomError("pipeline blew up")

    # The exception must propagate AND a failed event must have been emitted —
    # a version that swallows the exception would pass the "event emitted"
    # half but fail pytest.raises above; a version that never emits would
    # fail the assertion below. Both properties are required together.
    assert len(recorder.inserted_rows) == 1
    row = recorder.inserted_rows[0]
    assert row["status"] == "failed"
    assert row["step"] == workflow.OBLIGATION
    assert row["reason_code"], "a failed step must carry a reason code"


def test_step_timer_uses_explicit_reason_code_when_given(monkeypatch):
    recorder = _RecordingClient()
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: recorder)

    run_id = workflow.new_run_id()
    with pytest.raises(RuntimeError):
        with workflow.step_timer(workflow.PERSIST, run_id=run_id, reason_code="DB_ERROR"):
            raise RuntimeError("db exploded")

    row = recorder.inserted_rows[0]
    assert row["reason_code"] == "DB_ERROR"


def test_step_timer_still_reraises_when_persistence_itself_is_broken(monkeypatch):
    """Even if the recording machinery is fully broken, the original
    exception from the caller's block must still propagate — the timer's own
    best-effort persistence failure must never mask or replace it."""
    monkeypatch.setattr("db.client.get_client", lambda *a, **k: _BoomClient())

    run_id = workflow.new_run_id()
    with pytest.raises(ValueError, match="original failure"):
        with workflow.step_timer(workflow.REPORT, run_id=run_id):
            raise ValueError("original failure")
