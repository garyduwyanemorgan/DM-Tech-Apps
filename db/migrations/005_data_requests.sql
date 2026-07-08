-- ── Migration 005: Data & lab requests ──
-- Open requests raised by the algae/bloom engine: missing parameters to measure,
-- parameters that would strengthen the call, and confirmatory lab tests.
-- One row per request; status open → fulfilled/cancelled. Run in Supabase SQL editor.

CREATE TABLE IF NOT EXISTS public.data_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id     UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    reason      TEXT,
    items       TEXT[] NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'open',   -- open / fulfilled / cancelled
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS data_requests_site_id_idx ON public.data_requests (site_id);

-- Only the service-role backend touches this table. RLS on + explicit grant
-- (new SQL-editor tables don't always inherit the service_role default grant).
ALTER TABLE public.data_requests ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.data_requests TO service_role;
