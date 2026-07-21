BEGIN;

-- ── Migration 019: asset class + specification scope on assets ────────────────
-- `asset_type` (010) held two different kinds of thing in one flat list, which is
-- why the model did not hold together. Equipment — pump, filter, dosing, aerator
-- — are things you MAINTAIN: you backwash a filter, you service a dosing pump,
-- and nobody ever takes a laboratory sample from one. Sampled entities — water
-- body, water tank, fountain, washroom outlet, misting line — are things a
-- laboratory certificate is ABOUT: they carry samples, limits and a compliance
-- history. A maintenance category and a sampling location were competing for the
-- same field. `asset_class` separates them; see core/assets.py for the
-- authoritative taxonomy this column mirrors.
--
-- SCOPE MOVES TO THE ASSET. Scope ('lagoon' | 'facilities') decides which
-- specification set a result may be judged against — the safety boundary
-- described in 017. It was briefly modelled on report_types, which is the wrong
-- level: one asset carries many report types over time ("Gate Number 2 – GRP
-- Water Tank" has both microbiology and Legionella certificates), so scope would
-- have to be restated, consistently, on every type. And it is the asset that
-- actually decides the answer: a Legionella count of 900 CFU/L means one thing in
-- a stored domestic tank and another in an open animal moat. The asset does not
-- vary; the certificates attached to it do.
--
-- Requires 010 (assets) and 017 (report_types). Run in the Supabase SQL editor.
-- Reversible: see 019_asset_class_scope_down.sql.

ALTER TABLE public.assets
    ADD COLUMN IF NOT EXISTS asset_class TEXT,
    ADD COLUMN IF NOT EXISTS scope       TEXT;

ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_asset_class_check;
ALTER TABLE public.assets
    ADD CONSTRAINT assets_asset_class_check
    CHECK (asset_class IS NULL OR asset_class IN ('equipment', 'sampled'));

ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_check;
ALTER TABLE public.assets
    ADD CONSTRAINT assets_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities'));

-- Scope is only meaningful for something a certificate can be about. Equipment
-- has no specification set, so a scope on a dosing pump would be not merely
-- unused but misleading — it reads as "these limits apply" where no limits do.
-- Written as "scope IS NULL OR ..." so a sampled asset with no scope yet stays
-- legal: an unclassified sampled asset is a normal state, it simply cannot be
-- judged until someone says which specification set it lives under.
-- coalesce, not a bare equality: with asset_class NULL, `asset_class = 'sampled'`
-- evaluates to NULL, and Postgres accepts a CHECK that is not FALSE. A row with no
-- class but a scope set would therefore slip through — exactly the state this
-- constraint exists to forbid. coalesce forces a real TRUE/FALSE.
ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_requires_sampled_check;
ALTER TABLE public.assets
    ADD CONSTRAINT assets_scope_requires_sampled_check
    CHECK (scope IS NULL OR coalesce(asset_class, '') = 'sampled');

-- Backfill. The table holds two rows today — one asset_type='dosing', one with
-- asset_type NULL — and both are equipment: nothing sampled has been created yet,
-- because until now there was no way to say so. Guarded on IS NULL so re-running
-- this migration never overwrites a class someone has since set by hand.
UPDATE public.assets SET asset_class = 'equipment' WHERE asset_class IS NULL;

-- The upload flow lists sampled assets only ("which tank is this certificate
-- about?"), so every such lookup is org + class.
CREATE INDEX IF NOT EXISTS assets_org_class_idx ON public.assets (organization_id, asset_class);

COMMENT ON COLUMN public.assets.asset_class IS
    'equipment | sampled. equipment is maintained and never sampled (pump, filter, '
    'dosing, aerator); sampled is what a laboratory certificate is about (water '
    'body, water tank, fountain, washroom outlet, misting line). Mirrors '
    'core/assets.py — add a type there, not just here. Nullable so a legacy row '
    'can exist unclassified rather than be forced into the wrong half.';
COMMENT ON COLUMN public.assets.scope IS
    'lagoon | facilities. Selects the specification set a result on this asset may '
    'be judged against, and lives here because the asset is the stable thing: it '
    'outlives the report types attached to it, and it is what makes 900 CFU/L '
    'alarming in a domestic tank and ordinary in an animal moat. NULL is a real '
    'answer meaning "cannot be judged yet" — never default it, because defaulting '
    'applies one scope''s limits to the other scope''s asset and returns a '
    'confident wrong verdict. Only permitted when asset_class = ''sampled''.';

-- report_types.scope modelled the same idea one level too low (017). Leaving the
-- column in place would invite exactly the confusion this migration removes: two
-- sources of scope that can disagree, with no rule for which wins. It currently
-- holds 1 row of data ('tank' = facilities) and that value is discarded, which is
-- acceptable — scope now derives from the asset a certificate is attached to, so
-- the information is re-derived rather than lost.
ALTER TABLE public.report_types DROP COLUMN IF EXISTS scope;

COMMIT;
