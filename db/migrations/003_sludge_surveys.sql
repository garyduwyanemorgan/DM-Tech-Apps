-- ── Migration 003: Sludge & Sediment surveys ──
-- Per-site, per-zone sludge depth surveys. One row per (site, zone); re-surveying
-- a zone upserts it. Run this in your Supabase SQL editor.

CREATE TABLE IF NOT EXISTS public.sludge_surveys (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id          UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    zone_name        TEXT NOT NULL,
    total_depth_m    DOUBLE PRECISION NOT NULL,
    sludge_depth_m   DOUBLE PRECISION NOT NULL,
    survey_date      DATE NOT NULL DEFAULT CURRENT_DATE,
    updated_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (site_id, zone_name)
);

CREATE INDEX IF NOT EXISTS sludge_surveys_site_id_idx ON public.sludge_surveys (site_id);

-- Only the service-role backend touches this table (same as readings). Enable RLS
-- with no policies so anon/authenticated roles get zero access; service_role bypasses RLS.
ALTER TABLE public.sludge_surveys ENABLE ROW LEVEL SECURITY;

-- The backend authenticates as service_role. New tables created via the SQL editor
-- don't always inherit the default privilege grant, so grant it explicitly.
GRANT ALL ON public.sludge_surveys TO service_role;
