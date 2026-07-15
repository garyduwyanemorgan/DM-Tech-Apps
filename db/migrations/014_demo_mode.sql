BEGIN;

-- ── Migration 014: Demo mode ──────────────────────────────────────────────────
-- Self-service one-month demo. A super_admin clicks "Activate Demo"; the backend
-- provisions the key server-side (the user never sees or types it) and the org
-- gets full access — unlimited sites — until expires_at. After expiry the org is
-- read-only until it subscribes to a paid plan (the existing billing checkout is
-- the "switch to live" — no demo data is touched, everything carries over).
-- One demo per organization, ever: UNIQUE(organization_id).
-- Run in Supabase SQL editor (already applied 2026-07-15). Reversible: see
-- 014_demo_mode_down.sql.

CREATE TABLE IF NOT EXISTS public.demo_keys (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    key_code         TEXT NOT NULL UNIQUE,
    activated_by     TEXT,                               -- clerk id of the activating super_admin
    activated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id)
);
CREATE INDEX IF NOT EXISTS demo_keys_org_idx ON public.demo_keys (organization_id);

ALTER TABLE public.demo_keys ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.demo_keys TO service_role;

COMMIT;
