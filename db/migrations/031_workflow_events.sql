BEGIN;

-- ── Migration 031: Workflow (compliance pipeline) events ──
-- Append-only, per-entity record of which STEP of the compliance pipeline
--
--     ingest -> parse -> validate(gates) -> persist -> assess -> obligation -> report
--
-- ran, and whether it succeeded, failed, or was skipped, for one run/entity.
-- This is Layer 2: audit_events (006) answers "who did what and was it
-- authorized"; workflow_events answers "why is Site 7's March obligation still
-- non-compliant" — which pipeline step it stalled at and the reason code. That
-- is the differentiating feature of this product: customers do not ask "did the
-- server 500", they ask about one entity's compliance status. Written only by
-- the service-role backend via core/workflow.py. Run in Supabase SQL editor.
--
-- Reversible: see 031_workflow_events_down.sql.

-- Reuses the shared append-only guard from 006_audit_events.sql
-- (public.reject_mutation()) rather than redefining it. Per 006's reasoning:
-- a BEFORE UPDATE trigger blocks the tampering vector (altering recorded
-- history) without a BEFORE DELETE guard, because a DELETE guard here would
-- also block cascade deletes of parent rows, and only service_role can reach
-- this table at all regardless.
CREATE TABLE IF NOT EXISTS public.workflow_events (
    id               BIGSERIAL PRIMARY KEY,
    run_id           TEXT NOT NULL,        -- correlates every step of one pipeline run
    request_id       TEXT,                 -- HTTP request id, when the run started inside a request
    organization_id  UUID,                 -- denormalised; NO FK — same reasoning as audit_events (006/013):
                                            -- this log must survive independently of org lifecycle
    step             TEXT NOT NULL,        -- ingest / parse / validate / persist / assess / obligation / report
    status           TEXT NOT NULL,        -- ok / failed / skipped
    reason_code      TEXT,                 -- stable code explaining a failed/skipped outcome
    entity_type      TEXT,                 -- e.g. 'site', 'lab_sample', 'obligation'
    entity_id        TEXT,
    duration_ms      INTEGER,
    context          JSONB,                -- non-sensitive extra fields (no tokens/secrets)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_events_org_created_idx
    ON public.workflow_events (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workflow_events_run_idx
    ON public.workflow_events (run_id);
CREATE INDEX IF NOT EXISTS workflow_events_entity_idx
    ON public.workflow_events (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS workflow_events_status_idx
    ON public.workflow_events (status);

-- Enforce append-only, reusing 006's shared guard function.
DROP TRIGGER IF EXISTS workflow_events_no_mutate ON public.workflow_events;
CREATE TRIGGER workflow_events_no_mutate
    BEFORE UPDATE ON public.workflow_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

ALTER TABLE public.workflow_events ENABLE ROW LEVEL SECURITY;

-- This table is written by the backend only: the service_role client in
-- core/workflow.py (db.client.get_client(), unscoped), never by an
-- `authenticated` request-scoped client. So the only write grant is to
-- service_role, exactly like audit_events (006).
GRANT SELECT, INSERT ON public.workflow_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.workflow_events_id_seq TO service_role;

-- Unlike audit_events (which today has no authenticated-read policy at all),
-- this table is meant to answer a tenant-facing question — "why is my
-- obligation still non-compliant" — so authenticated callers can read their
-- own organisation's rows. Follows 029's post-fix convention: the
-- organisation predicate alone, with no super_admin cross-tenant clause (029
-- removed that clause everywhere it did not carry a matching organisation
-- test, and none is added here).
DROP POLICY IF EXISTS select_workflow_events ON public.workflow_events;
CREATE POLICY select_workflow_events ON public.workflow_events
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
  );

COMMIT;
