-- ── Migration 004: Sludge depths to metric (feet → metres) ──
-- Renames the depth columns to metres. Guarded so it is a no-op on fresh installs
-- (which already create *_m columns via the updated 003). Run in Supabase SQL editor.
--
-- NOTE: this renames columns only. Existing values are overwritten by the app's
-- re-seed with metric depths; if you have real feet data to preserve, run the
-- optional UPDATE at the bottom to convert it in place before re-seeding.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sludge_surveys' AND column_name = 'total_depth_ft') THEN
    ALTER TABLE public.sludge_surveys RENAME COLUMN total_depth_ft TO total_depth_m;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sludge_surveys' AND column_name = 'sludge_depth_ft') THEN
    ALTER TABLE public.sludge_surveys RENAME COLUMN sludge_depth_ft TO sludge_depth_m;
  END IF;
END $$;

-- Optional — only if you had REAL feet measurements to preserve (skip if re-seeding):
-- UPDATE public.sludge_surveys
--   SET total_depth_m = total_depth_m * 0.3048,
--       sludge_depth_m = sludge_depth_m * 0.3048;
