-- ── Migration 007: Scope model — business units, projects, and assignments ──
-- Adds the scope dimensions required by PERMISSIONS_MATRIX.md (§Required scope
-- dimensions): business unit → project/contract → site, plus user→site and
-- user→project assignments. Enforcement is app-layer (service-role bypasses RLS);
-- these tables give the backend the data to scope every query (priority gap #1).
-- Run in Supabase SQL editor. Reversible: see 007_assignments_down.sql.
--
-- SAFE-ON-POPULATED-DB NOTES:
--  * All additions are new tables or NULLABLE columns — no existing row breaks.
--  * sites.project_id / sites.business_unit_id are added NULL; backfill later.
--  * Scope ENFORCEMENT stays behind the SCOPE_ENFORCEMENT flag in the backend
--    until every existing user has been backfilled with assignments, so turning
--    the tables on does not lock anyone out (see PERMISSIONS_REVIEW_PACKAGE.md §8).

-- Business unit hierarchy (self-referential tree, org-scoped).
CREATE TABLE IF NOT EXISTS public.business_units (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    parent_id        UUID REFERENCES public.business_units(id) ON DELETE SET NULL,
    name             TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, name)
);
CREATE INDEX IF NOT EXISTS business_units_org_idx ON public.business_units (organization_id);
CREATE INDEX IF NOT EXISTS business_units_parent_idx ON public.business_units (parent_id);

-- Project / contract (Project-Manager authority boundary).
CREATE TABLE IF NOT EXISTS public.projects (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    business_unit_id UUID REFERENCES public.business_units(id) ON DELETE SET NULL,
    name             TEXT NOT NULL,
    contract_ref     TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, name)
);
CREATE INDEX IF NOT EXISTS projects_org_idx ON public.projects (organization_id);
CREATE INDEX IF NOT EXISTS projects_bu_idx ON public.projects (business_unit_id);

-- Place existing sites into the hierarchy (nullable; backfill deliberately).
ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS project_id UUID
    REFERENCES public.projects(id) ON DELETE SET NULL;
ALTER TABLE public.sites ADD COLUMN IF NOT EXISTS business_unit_id UUID
    REFERENCES public.business_units(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS sites_project_idx ON public.sites (project_id);

-- user_profiles.clerk_id is the stable per-user key used across the app; assignment
-- rows reference it. (clerk_id is UNIQUE per 002_clerk.)
CREATE TABLE IF NOT EXISTS public.user_site_assignments (
    user_clerk_id    TEXT NOT NULL,
    site_id          UUID NOT NULL REFERENCES public.sites(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    assigned_by      TEXT,
    assigned_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_clerk_id, site_id)
);
CREATE INDEX IF NOT EXISTS usa_site_idx ON public.user_site_assignments (site_id);
CREATE INDEX IF NOT EXISTS usa_org_user_idx ON public.user_site_assignments (organization_id, user_clerk_id);

CREATE TABLE IF NOT EXISTS public.user_project_assignments (
    user_clerk_id    TEXT NOT NULL,
    project_id       UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    assigned_by      TEXT,
    assigned_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_clerk_id, project_id)
);
CREATE INDEX IF NOT EXISTS upa_project_idx ON public.user_project_assignments (project_id);
CREATE INDEX IF NOT EXISTS upa_org_user_idx ON public.user_project_assignments (organization_id, user_clerk_id);

-- Also index user_profiles.organization_id (seq-scanned by get_user_organization
-- and member listing today; DB audit §5).
CREATE INDEX IF NOT EXISTS user_profiles_org_idx ON public.user_profiles (organization_id);

ALTER TABLE public.business_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_site_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_project_assignments ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.business_units TO service_role;
GRANT ALL ON public.projects TO service_role;
GRANT ALL ON public.user_site_assignments TO service_role;
GRANT ALL ON public.user_project_assignments TO service_role;
