-- ── Rollback for Migration 007 ──
DROP INDEX IF EXISTS public.sites_project_idx;
ALTER TABLE public.sites DROP COLUMN IF EXISTS project_id;
ALTER TABLE public.sites DROP COLUMN IF EXISTS business_unit_id;
DROP TABLE IF EXISTS public.user_project_assignments;
DROP TABLE IF EXISTS public.user_site_assignments;
DROP TABLE IF EXISTS public.projects;
DROP TABLE IF EXISTS public.business_units;
DROP INDEX IF EXISTS public.user_profiles_org_idx;
