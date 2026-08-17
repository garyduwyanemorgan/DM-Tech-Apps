-- ── 032 DOWN: drop the self-serve provisioning function ──
--
-- Nothing in the application calls public.bootstrap_self_serve_profile() — 032's
-- header says so explicitly — so dropping it removes a capability that was never
-- wired to anything, not a live code path. No data loss: the function has no
-- state of its own, and any organisation/profile rows it was used to create
-- (live-test rows only; see tests/test_bootstrap_migration.py) remain untouched
-- by dropping the function that created them.
--
-- One function only.

BEGIN;

DROP FUNCTION IF EXISTS public.bootstrap_self_serve_profile();

COMMIT;
