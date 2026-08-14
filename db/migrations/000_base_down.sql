BEGIN;

-- ── Rollback for 000_base.sql ────────────────────────────────────────────────
-- DESTRUCTIVE, and more so than any other _down file in this directory: it drops
-- the two tables holding every monthly reading and every forward prediction.
-- There is no other copy of that data in the schema — 016's lab_samples work is
-- explicit that `readings` was left untouched and holds its own separate data.
--
-- This exists for one situation only: a bootstrap of a NEW project that went
-- wrong and needs restarting from empty. If the database has real data in it,
-- you want a backup, not this file.
--
-- CASCADE is required rather than optional: db/schema.sql adds site_id foreign
-- keys onto both tables, and schema_rls.sql attaches policies to them.
DROP TABLE IF EXISTS public.predictions CASCADE;
DROP TABLE IF EXISTS public.readings CASCADE;

-- Dropped last. While it exists, db/guard.py can still identify which database
-- this is — which is exactly what you want if a rollback is interrupted
-- part-way and someone has to work out what they are looking at.
DROP TABLE IF EXISTS public.deployment_identity CASCADE;

COMMIT;
