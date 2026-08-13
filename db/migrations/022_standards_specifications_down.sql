BEGIN;

-- ── Rollback for Migration 022 ────────────────────────────────────────────────
-- Drops the standards registry and specification sets.
--
-- LOSSY BY DESIGN, but recoverably so. Everything these tables hold is seeded
-- from Python (core/standards.py KNOWN_EDITIONS, core/constants.py
-- COMPLIANCE_LIMITS) by a seeder that can simply be re-run, so built-in content
-- is reproducible. What is NOT reproducible is anything a tenant created:
--
--   * organisation-specific specification_sets and their spec_limits
--   * any standards edition added by hand rather than by the seeder
--   * verified_by / verified_on provenance recorded after seeding
--
-- If any organisation has created its own specification set, EXPORT IT BEFORE
-- RUNNING THIS. There is no way to reconstruct a client's own limits from code.
--
-- Ordering: children before parents. spec_limits references specification_sets,
-- which references standards, and standards references itself. The CASCADE on
-- spec_limits.spec_set_id would handle the first hop automatically, but dropping
-- explicitly in dependency order keeps the intent obvious and does not rely on
-- cascade behaviour to be correct.
--
-- NOTE ON POLICIES. There are deliberately no DROP POLICY statements here.
-- Policies, indexes and constraints are dropped with their table, so they would
-- be redundant — and worse than redundant: `DROP POLICY IF EXISTS p ON t` only
-- tolerates a missing POLICY, not a missing TABLE. If `t` does not exist it
-- raises 42P01, which inside this BEGIN…COMMIT aborts the entire rollback
-- including the DROP TABLEs that would have cleaned up. That failure mode is
-- worst in exactly the partial-state case such statements look like they are
-- protecting against. (016_lab_samples_down.sql has that shape; it works only
-- because its tables are always present when it runs.)

DROP TABLE IF EXISTS public.spec_limits;
DROP TABLE IF EXISTS public.specification_sets;

-- standards last: specification_sets.standard_id is ON DELETE RESTRICT, so this
-- would fail while any set still referenced it. By this point that table is
-- gone, so the restriction has nothing left to protect. The self-referencing
-- supersedes_id FK needs no special handling — DROP TABLE removes the whole
-- relation and its constraints together.
DROP TABLE IF EXISTS public.standards;

COMMIT;
