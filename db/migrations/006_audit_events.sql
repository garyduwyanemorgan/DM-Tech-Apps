BEGIN;

-- ── Migration 006: Security & operational audit events ──
-- Append-only, immutable record of authorization denials and sensitive mutations
-- (role changes, user removal, site/sludge deletion, report finalization, billing
-- and stock changes). Backs the audit.read permission and regulatory traceability
-- (PERMISSIONS_MATRIX.md rows 76, 128; priority gaps #5). Written only by the
-- service-role backend via core/audit.py. Run in Supabase SQL editor.
--
-- Reversible: see 006_audit_events_down.sql.

-- Shared immutability guard: reused by every append-only table (ledgers, event
-- logs). REVOKE alone does not stop a table-owning/bypassing role, so enforce in
-- a trigger that rejects UPDATE (the tampering vector — altering recorded
-- history). The triggers below fire BEFORE UPDATE only, NOT DELETE: a BEFORE
-- DELETE guard also blocks cascade deletes, which would make parent rows (orgs,
-- corrective actions, inventory items) undeletable. Deleting a whole parent is an
-- administrative action, not record tampering, and only service_role can reach
-- these tables at all.
CREATE OR REPLACE FUNCTION public.reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table %.% is append-only; % is not permitted',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS public.audit_events (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  UUID,                 -- denormalised; NO FK: audit log is independent of org lifecycle (see 013)
    actor_user_id    TEXT,                 -- Clerk user id (NULL for anonymous denials)
    actor_role       TEXT,
    action           TEXT NOT NULL,        -- e.g. 'site.delete','user.role.assign','authz.denied'
    outcome          TEXT NOT NULL DEFAULT 'success',  -- success / denied / error
    target_type      TEXT,
    target_id        TEXT,
    context          JSONB,                -- non-sensitive extra fields (no tokens/secrets)
    ip               TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_events_org_created_idx
    ON public.audit_events (organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_target_idx
    ON public.audit_events (target_type, target_id);
CREATE INDEX IF NOT EXISTS audit_events_action_idx
    ON public.audit_events (action, created_at DESC);

-- Enforce append-only.
DROP TRIGGER IF EXISTS audit_events_no_mutate ON public.audit_events;
CREATE TRIGGER audit_events_no_mutate
    BEFORE UPDATE ON public.audit_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;
GRANT SELECT, INSERT ON public.audit_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.audit_events_id_seq TO service_role;

COMMIT;
