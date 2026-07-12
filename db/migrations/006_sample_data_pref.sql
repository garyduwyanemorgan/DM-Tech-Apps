-- 006_sample_data_pref.sql
-- Per-user sample-data preference.
--
-- The sample/demo toggle used to live in localStorage, so it was per-browser and
-- silently reset on a new device. It is now part of the user's profile: one user,
-- one setting, everywhere they sign in.
--
-- Default TRUE preserves today's behaviour for existing users (sample data on).

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS show_sample_data BOOLEAN NOT NULL DEFAULT TRUE;
