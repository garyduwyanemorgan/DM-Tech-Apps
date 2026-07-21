BEGIN;

-- ── Migration 017: Organisation-defined report types ──
-- The upload flow offers a report type per certificate. Built-in types live in
-- code (core/report_types.py); this table holds the ones an organisation adds
-- for itself. Requires 006/007 (organizations). Run in the Supabase SQL editor.
-- Reversible: see 017_report_types_down.sql.
--
-- A report type carries a SCOPE, and scope is a safety boundary rather than a
-- category. It decides which specification set a result may be judged against.
-- The two scopes share many parameter names (pH, turbidity, ammonia, phosphate,
-- E. coli, total coliforms, COD), so without it a facilities-management sample
-- could be assessed against recreational-lagoon limits and come back green.
--
-- Fields are deliberately NOT stored here. A custom type's parameters are
-- whatever the extraction finds on the certificate, so the document stays the
-- source of truth and a type definition can never silently disagree with it.

CREATE TABLE IF NOT EXISTS public.report_types (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    scope            TEXT NOT NULL
                     CHECK (scope IN ('lagoon', 'facilities')),
    created_by       TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    -- Case-sensitive at the column level; the API normalises whitespace and
    -- compares case-insensitively before inserting, so "Cooling Tower" and
    -- "cooling tower" cannot both be created.
    UNIQUE (organization_id, name)
);

CREATE INDEX IF NOT EXISTS report_types_org_idx ON public.report_types (organization_id);

COMMENT ON COLUMN public.report_types.scope IS
    'lagoon | facilities. Selects the specification set used to judge results. '
    'Never infer this from parameter names — the two scopes overlap, and judging '
    'a facilities sample against lagoon limits returns a confident wrong verdict.';

ALTER TABLE public.report_types ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.report_types TO service_role;

-- Policies follow schema_rls.sql: org-scoped read, admin/operator mutate.
DROP POLICY IF EXISTS select_report_types ON public.report_types;
CREATE POLICY select_report_types ON public.report_types
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_report_types ON public.report_types;
CREATE POLICY mutate_report_types ON public.report_types
  FOR ALL USING (
    (organization_id = public.get_user_organization()
     AND public.get_user_role() IN ('admin', 'operator', 'super_admin'))
  );

COMMIT;
