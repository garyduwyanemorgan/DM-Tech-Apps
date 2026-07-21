BEGIN;

-- ── Migration 016: Laboratory samples & per-parameter results ─────────────────
-- Ingestion target for external laboratory PDF reports (Wimpey Laboratories,
-- Dubai Safari Park). `readings` is UNIQUE(site_id, year, month) — one aggregated
-- row per site per month — and cannot represent lab work: sampling happens per
-- sampling point, several times a month, with per-parameter method/unit/LOQ/
-- specification metadata and a pass/fail verdict. These two tables hold that;
-- `readings` is deliberately left untouched, so the monthly dashboard keeps
-- working while lab data lands alongside it.
--
-- lab_samples  = one row per lab report (header/chain-of-custody fields).
-- lab_results  = one row per parameter measured on that report.
--
-- Both carry a forensic audit trail: raw_extraction (the extractor's verbatim
-- output) and value_raw (the lab's verbatim result text). See the COMMENT ON
-- COLUMN blocks below before touching either. Requires 006 (reject_mutation),
-- 007 (sites) and 010 (assets). Run in Supabase SQL editor.
-- Reversible: see 016_lab_samples_down.sql.

CREATE TABLE IF NOT EXISTS public.lab_samples (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id        UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id                UUID REFERENCES public.sites(id) ON DELETE CASCADE,
    asset_id               UUID REFERENCES public.assets(id) ON DELETE SET NULL,  -- lagoon/water body (010)
    laboratory             TEXT,                 -- e.g. 'Wimpey Laboratories'
    report_no              TEXT NOT NULL,
    form_type              TEXT,                 -- WRF1-W-001 / WRF2-W-001 / WRF2-W-002
    report_type            TEXT,                 -- chemistry / microbiology / legionella / scanned
    sampling_point         TEXT,
    sample_location        TEXT,
    sample_identification  TEXT,
    source_of_sample       TEXT,
    sample_description     TEXT,
    sampled_at             DATE,
    received_at            DATE,
    reported_at            DATE,
    analysis_start         DATE,
    analysis_end           DATE,
    sampling_time          TEXT,                 -- free text on the form ('09:45', '9.45 am')
    sampled_by             TEXT,
    sampling_method        TEXT,
    sampling_apparatus     TEXT,
    sample_volume          TEXT,                 -- verbatim ('500 mL', '1 L')
    temperature_c          NUMERIC,
    analyst                TEXT,
    reviewed_by            TEXT,                 -- the laboratory's reviewer, not ours
    remarks                TEXT,
    source_filename        TEXT,
    source_sha256          TEXT,                 -- ties the row to the exact PDF byte-for-byte
    extraction_method      TEXT,                 -- wimpey-pdf-text / claude-vision
    extraction_confidence  NUMERIC,
    reviewer_status        TEXT NOT NULL DEFAULT 'pending'
                             CHECK (reviewer_status IN ('pending','approved','corrected','rejected')),
    anomalies              JSONB,                -- extractor/validator findings for human review
    raw_extraction         JSONB NOT NULL,
    created_at             TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, report_no)
);
CREATE INDEX IF NOT EXISTS lab_samples_org_site_idx    ON public.lab_samples (organization_id, site_id);
CREATE INDEX IF NOT EXISTS lab_samples_sampled_at_idx  ON public.lab_samples (sampled_at DESC);
CREATE INDEX IF NOT EXISTS lab_samples_asset_idx       ON public.lab_samples (asset_id);
CREATE INDEX IF NOT EXISTS lab_samples_review_idx      ON public.lab_samples (organization_id, reviewer_status);
CREATE INDEX IF NOT EXISTS lab_samples_sha_idx         ON public.lab_samples (source_sha256);

COMMENT ON COLUMN public.lab_samples.raw_extraction IS
    'IMMUTABLE forensic audit trail: the extractor''s verbatim output for this '
    'report, exactly as produced, before any normalisation. It is the evidence '
    'that the typed columns above faithfully represent the PDF, and it is what a '
    'regulator, client or dispute is re-read against. Do NOT prune keys, do NOT '
    'reshape it to match the current parser, do NOT rewrite it when extraction '
    'improves — re-ingest into a new row instead. Enforced by the '
    'lab_samples_raw_extraction_immutable trigger (UPDATE is rejected if this '
    'column changes); every other column stays editable so reviewers can correct '
    'the parsed values and set reviewer_status.';
COMMENT ON COLUMN public.lab_samples.reviewer_status IS
    'Our review state of the extraction: pending -> approved / corrected / rejected. '
    'Nothing downstream should trust a row that is still pending or rejected.';
COMMENT ON COLUMN public.lab_samples.source_sha256 IS
    'SHA-256 of the source PDF. Proves which file a row came from and makes '
    're-ingestion of an identical document detectable.';

CREATE TABLE IF NOT EXISTS public.lab_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_id       UUID NOT NULL REFERENCES public.lab_samples(id) ON DELETE CASCADE,
    parameter       TEXT NOT NULL,        -- 'pH', 'Total Coliform', 'Legionella pneumophila' …
    test_method     TEXT,                 -- 'APHA 4500-H+ B', 'ISO 11731' …
    unit            TEXT,
    value_raw       TEXT NOT NULL,
    value_num       NUMERIC,              -- NULL whenever value_raw is not a plain number
    qualifier       TEXT,                 -- '<' / '>' / 'ND' / NULL
    loq             NUMERIC,              -- limit of quantification
    mou             TEXT,                 -- measurement uncertainty, verbatim ('± 0.2')
    specification   TEXT,                 -- the limit the lab assessed against, verbatim
    status          TEXT CHECK (status IN ('PASS','FAIL','NOT_ASSESSED'))
);
CREATE INDEX IF NOT EXISTS lab_results_sample_idx     ON public.lab_results (sample_id);
CREATE INDEX IF NOT EXISTS lab_results_parameter_idx  ON public.lab_results (parameter);
CREATE INDEX IF NOT EXISTS lab_results_status_idx     ON public.lab_results (status);

COMMENT ON COLUMN public.lab_results.value_raw IS
    'The laboratory''s VERBATIM result text — ''<1'', ''Not Detected'', ''30.4'', '
    '''Absent/100mL''. This is the legally reportable value; the typed columns are '
    'derived conveniences. NEVER coerce it to 0 and never "tidy" it: ''<1'' means '
    '"below the limit of quantification", which is regulatorily distinct from a '
    'measured 0, and ''Not Detected'' is distinct again. Collapsing them silently '
    'turns a compliant non-detect into a fabricated measurement.';
COMMENT ON COLUMN public.lab_results.value_num IS
    'Numeric form for charting/aggregation ONLY, and deliberately NULLABLE: it is '
    'NULL whenever value_raw is non-numeric (''<1'', ''Not Detected''). Do not '
    'backfill those NULLs with 0 or with the LOQ — surface the NULL and let '
    'value_raw/qualifier carry the meaning.';
COMMENT ON COLUMN public.lab_results.qualifier IS
    'Parsed sense of a non-numeric value_raw: ''<'' (below LOQ), ''>'' (above '
    'range), ''ND'' (not detected), NULL for a plain number.';

-- Immutability guard for the forensic payload. The whole-table append-only
-- pattern (006/012, reject_mutation) is too strong here: reviewers must be able
-- to correct parsed fields and move reviewer_status along. So we guard the one
-- column that must never change, using the same "reject in a trigger, because
-- REVOKE does not stop a bypassing role" reasoning as 006.
CREATE OR REPLACE FUNCTION public.reject_raw_extraction_change() RETURNS trigger AS $$
BEGIN
    IF NEW.raw_extraction IS DISTINCT FROM OLD.raw_extraction THEN
        RAISE EXCEPTION
            '%.%.raw_extraction is an immutable forensic record; re-ingest the report instead of updating it',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS lab_samples_raw_extraction_immutable ON public.lab_samples;
CREATE TRIGGER lab_samples_raw_extraction_immutable
    BEFORE UPDATE ON public.lab_samples
    FOR EACH ROW EXECUTE FUNCTION public.reject_raw_extraction_change();

ALTER TABLE public.lab_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lab_results ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.lab_samples TO service_role;
GRANT ALL ON public.lab_results TO service_role;

-- Policies follow schema_rls.sql. lab_samples is org-scoped directly (the sites
-- pattern); lab_results has no organization_id, so it is scoped through its
-- parent sample exactly as readings/predictions are scoped through sites.
DROP POLICY IF EXISTS select_lab_samples ON public.lab_samples;
CREATE POLICY select_lab_samples ON public.lab_samples
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_lab_samples ON public.lab_samples;
CREATE POLICY mutate_lab_samples ON public.lab_samples
  FOR ALL USING (
    (organization_id = public.get_user_organization()
     AND public.get_user_role() IN ('admin', 'operator', 'super_admin'))
  );

DROP POLICY IF EXISTS select_lab_results ON public.lab_results;
CREATE POLICY select_lab_results ON public.lab_results
  FOR SELECT USING (
    sample_id IN (SELECT id FROM public.lab_samples WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_lab_results ON public.lab_results;
CREATE POLICY mutate_lab_results ON public.lab_results
  FOR ALL USING (
    (sample_id IN (SELECT id FROM public.lab_samples WHERE organization_id = public.get_user_organization())
     AND public.get_user_role() IN ('admin', 'operator', 'super_admin'))
  );

COMMIT;
