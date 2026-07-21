BEGIN;

-- ── Migration 020: organisation-defined asset types ──
-- The asset taxonomy was hardcoded in core/assets.py: nine fixed types, so
-- adding "GRP Tank" or "Wet Moat" meant a deploy. This table lets an
-- organisation extend it from Settings → Asset Register. Built-ins stay in code
-- and are always offered; these are additions, not replacements.
-- Requires 006/007 (organizations) and 019 (asset_class/scope on assets).
-- Run in the Supabase SQL editor. Reversible: 020_asset_types_down.sql.
--
-- A type declares its CLASS and, for sampled types, its SCOPE. Both are
-- mandatory for sampled types: an asset type that cannot say which specification
-- set governs it produces certificates nothing can judge. This is the taxonomy
-- equivalent of the guard in core/assets.scope_of_asset().
--
-- Instances COPY class and scope from the type at creation rather than
-- referencing it. Editing a type must not silently re-judge certificates already
-- filed against assets created under the old definition — same reasoning as the
-- immutable raw_extraction in 016.

CREATE TABLE IF NOT EXISTS public.asset_types (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    key              TEXT NOT NULL,          -- machine name, e.g. grp_tank
    label            TEXT NOT NULL,          -- shown in dropdowns, e.g. "GRP Tank"
    asset_class      TEXT NOT NULL
                     CHECK (asset_class IN ('equipment', 'sampled')),
    scope            TEXT
                     CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities')),
    created_by       TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, key),
    -- Equipment never carries a scope; a sampled type must. coalesce, not a bare
    -- equality: with asset_class NULL a plain comparison yields NULL, and Postgres
    -- accepts a CHECK that is not FALSE.
    CONSTRAINT asset_types_scope_matches_class
        CHECK (
            (coalesce(asset_class, '') = 'sampled'   AND scope IS NOT NULL)
         OR (coalesce(asset_class, '') = 'equipment' AND scope IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS asset_types_org_class_idx
    ON public.asset_types (organization_id, asset_class);

COMMENT ON COLUMN public.asset_types.scope IS
    'lagoon | facilities. Required for sampled types, forbidden for equipment. '
    'Assets copy this at creation; changing it here never re-judges existing ones.';
COMMENT ON COLUMN public.asset_types.key IS
    'Stable machine name stored on assets.asset_type. Renaming the label is safe; '
    'changing the key would orphan every asset already using it.';

ALTER TABLE public.asset_types ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.asset_types TO service_role;

DROP POLICY IF EXISTS select_asset_types ON public.asset_types;
CREATE POLICY select_asset_types ON public.asset_types
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_asset_types ON public.asset_types;
CREATE POLICY mutate_asset_types ON public.asset_types
  FOR ALL USING (
    (organization_id = public.get_user_organization()
     AND public.get_user_role() IN ('admin', 'super_admin'))
  );

COMMIT;
