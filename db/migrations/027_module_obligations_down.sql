BEGIN;

-- ── Rollback for 027_module_obligations.sql ─────────────────────────────────
-- Dropping module_obligations severs every instance's link to the template it
-- came from. The obligations themselves survive — the FK is ON DELETE SET NULL —
-- and so does their evidence, which is the point of §7.5. What is lost is the
-- ability to tell which client duties were derived from a guideline and which
-- were typed in by hand, and therefore the ability to diff a new edition against
-- what clients are tracking.
--
-- The column is dropped before the table so the FK goes with it cleanly rather
-- than relying on CASCADE to reach into obligations.

DROP INDEX IF EXISTS public.obligations_module_obligation_idx;
ALTER TABLE public.obligations DROP COLUMN IF EXISTS module_obligation_id;

DROP TABLE IF EXISTS public.module_obligations;

COMMIT;
