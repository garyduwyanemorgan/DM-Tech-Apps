BEGIN;

-- ── Migration 015: site street address ────────────────────────────────────────
-- Free-text address per site, shown in Site Manager and pinned on the Google
-- Maps embed below the Configured Sites panel (the active site's pin). No
-- geocoding stored — the embed resolves the address itself. Additive + nullable;
-- safe on a populated database. Run in Supabase SQL editor.
-- Reversible: see 015_site_address_down.sql.

ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS address TEXT;

COMMIT;
