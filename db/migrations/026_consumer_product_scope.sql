BEGIN;

-- ── Migration 026: add 'consumer_product' to the scope vocabulary ────────────
-- WHY. Loading the extracted corpus refused ten specification sets from GU116
-- and GU117 because their `applies_to_scope` is 'consumer_product', which 022's
-- CHECK does not permit. The value is not an extraction error: those guidelines
-- govern cosmetics, oral hygiene products, perfumes and fragrances — things
-- placed on a market, not facilities operated on a site. Forcing them into
-- 'facilities' would be a lie in a column whose whole job is preventing one
-- scope's limits from being applied to another scope's asset (§7.4, and the
-- assets.scope comment in 019).
--
-- WHAT THIS DOES NOT DECIDE. §7.11 records that this family sells to traders and
-- importers rather than FM contractors, and asks whether it is the same product
-- at all. This migration does not answer that. A scope is a statement about what
-- kind of thing is being judged; whether we sell modules for it is decided by
-- guideline_modules and organization_entitlements, and every module the loader
-- creates is 'unverified' / 'coming_soon' regardless. Letting the content load
-- and be inspected is a prerequisite for that decision, not a commitment to it.
--
-- THREE CHECKS, NOT TWO. 022's header says the scope CHECK on specification_sets
-- and the one on assets "must be widened together". There are in fact three:
-- migration 020 added asset_types.scope with its own copy. All three are widened
-- here, in one file, because the failure mode of missing one is silent and
-- specific — a scope legal on an asset but illegal on a specification set is an
-- asset that can never be judged, and a scope legal on a specification set but
-- illegal on an asset type is a limit set nothing can ever be classified into.
--
-- If a fourth copy is ever added, add it to this list rather than to a new file.

ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_check;
ALTER TABLE public.assets
    ADD CONSTRAINT assets_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities', 'consumer_product'));

ALTER TABLE public.asset_types DROP CONSTRAINT IF EXISTS asset_types_scope_check;
ALTER TABLE public.asset_types
    ADD CONSTRAINT asset_types_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities', 'consumer_product'));

ALTER TABLE public.specification_sets DROP CONSTRAINT IF EXISTS specification_sets_scope_check;
ALTER TABLE public.specification_sets
    ADD CONSTRAINT specification_sets_scope_check
    CHECK (applies_to_scope IS NULL
           OR applies_to_scope IN ('lagoon', 'facilities', 'consumer_product'));

COMMENT ON COLUMN public.specification_sets.applies_to_scope IS
    'Mirrors assets.scope and asset_types.scope — all three CHECKs are widened '
    'together (026 is the model). NULL means the set is not scope-restricted and '
    'must be selected explicitly. Never default this: a defaulted scope produces '
    'a confident wrong verdict, which is the failure §7.4 names as central and '
    'the assets.scope comment in 019 explains at length. '
    'consumer_product (026) covers guidelines governing goods placed on a market '
    'rather than a site operated under an FM contract — a different regulated '
    'party, which is why §7.11 leaves open whether those modules are this product '
    'or an adjacent one.';

COMMIT;
