BEGIN;

-- ── Migration 008: Corrective-action workflow ──
-- Owner, due date, severity, status transitions, evidence, and an append-only,
-- immutable event history (PERMISSIONS_MATRIX.md rows 51-53). Site Supervisors
-- execute assigned actions; Managers/Executive assign and approve closure;
-- General Managers are read-only. Requires 006 (reject_mutation) and 007 (sites
-- already have project/BU). Run in Supabase SQL editor.
-- Reversible: see 008_corrective_actions_down.sql.

CREATE TABLE IF NOT EXISTS public.corrective_actions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id          UUID REFERENCES public.sites(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    description      TEXT,
    severity         TEXT,                 -- info / low / medium / high / critical
    status           TEXT NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open','in_progress','pending_approval','closed','cancelled')),
    owner_clerk_id   TEXT,                 -- assigned executor (a Site Supervisor)
    due_date         DATE,
    created_by       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_by        TEXT,
    closed_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ca_org_status_idx ON public.corrective_actions (organization_id, status);
CREATE INDEX IF NOT EXISTS ca_site_idx ON public.corrective_actions (site_id);
CREATE INDEX IF NOT EXISTS ca_owner_idx ON public.corrective_actions (owner_clerk_id);

-- Immutable history: assignment, progress notes, evidence, status transitions,
-- closure approval. One row per event; never updated or deleted.
CREATE TABLE IF NOT EXISTS public.corrective_action_events (
    id               BIGSERIAL PRIMARY KEY,
    action_id        UUID NOT NULL REFERENCES public.corrective_actions(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    event_type       TEXT NOT NULL,        -- created / assigned / progress / status_change / evidence / closed
    from_status      TEXT,
    to_status        TEXT,
    actor_clerk_id   TEXT,
    note             TEXT,
    evidence_url     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cae_action_idx ON public.corrective_action_events (action_id, created_at);

DROP TRIGGER IF EXISTS cae_no_mutate ON public.corrective_action_events;
CREATE TRIGGER cae_no_mutate
    BEFORE UPDATE OR DELETE ON public.corrective_action_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

ALTER TABLE public.corrective_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.corrective_action_events ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.corrective_actions TO service_role;
GRANT SELECT, INSERT ON public.corrective_action_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.corrective_action_events_id_seq TO service_role;

COMMIT;
