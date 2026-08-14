BEGIN;

-- ── Rollback for 026_consumer_product_scope.sql ─────────────────────────────
-- LOSSY IN A WAY THAT ABORTS RATHER THAN CORRUPTS. Narrowing the CHECK back will
-- FAIL if any asset, asset type or specification set is already scoped
-- 'consumer_product'. That is the intended behaviour: the alternative is either
-- deleting those rows, which destroys limit sets somebody may be judging against,
-- or rewriting their scope to 'facilities', which would silently assert that a
-- cosmetics limit governs a building.
--
-- If you need this rollback with such rows present, decide what happens to them
-- first and do it as its own migration. There is no safe automatic answer.
--
-- Order matters only in that all three must move together — a half-narrowed
-- vocabulary is the exact inconsistency 026 exists to prevent.

ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_check;
ALTER TABLE public.assets
    ADD CONSTRAINT assets_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities'));

ALTER TABLE public.asset_types DROP CONSTRAINT IF EXISTS asset_types_scope_check;
ALTER TABLE public.asset_types
    ADD CONSTRAINT asset_types_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities'));

ALTER TABLE public.specification_sets DROP CONSTRAINT IF EXISTS specification_sets_scope_check;
ALTER TABLE public.specification_sets
    ADD CONSTRAINT specification_sets_scope_check
    CHECK (applies_to_scope IS NULL OR applies_to_scope IN ('lagoon', 'facilities'));

COMMIT;
