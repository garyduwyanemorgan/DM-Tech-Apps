BEGIN;

-- ── Migration 021: record which asset TYPE a certificate is about ──
-- The upload flow asks for a sampled asset type (Settings → Asset Register), not
-- always a specific instance: a consultant knows the certificate is about a water
-- tank before the tank has been registered as an asset. lab_samples.asset_id
-- covers the instance case and stays; this records the type either way.
--
-- Stored by value, like asset_class and scope on assets: renaming or removing a
-- type later must not change what an already-filed certificate says it was about.
-- Requires 016. Reversible: 021_lab_samples_asset_type_down.sql.

ALTER TABLE public.lab_samples
    ADD COLUMN IF NOT EXISTS asset_type TEXT;

CREATE INDEX IF NOT EXISTS lab_samples_asset_type_idx
    ON public.lab_samples (organization_id, asset_type);

COMMENT ON COLUMN public.lab_samples.asset_type IS
    'Sampled asset type key the certificate is about (e.g. water_tank, grp_tank). '
    'Recorded by value — the scope actually applied is derived from this at save '
    'time and must not be re-derived later, since the register can change.';

COMMIT;
