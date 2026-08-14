BEGIN;

-- ── Migration 000: the tables that were never in the repo ─────────────────────
-- Numbered 000 because it must run BEFORE db/schema.sql, which is otherwise the
-- first file in the bootstrap order.
--
-- WHY THIS EXISTS. This repo could not stand up a new database. db/schema.sql
-- opens with `ALTER TABLE readings ADD COLUMN ...` and schema_rls.sql enables RLS
-- on `predictions` — but neither table is CREATEd anywhere in the repository. The
-- original database was built incrementally in the Supabase dashboard, and the
-- DDL for the two oldest tables only ever existed inside that project. Every file
-- written since has assumed them. Applying schema.sql to an empty database fails
-- on its first statement.
--
-- That mattered little while there was one database. It matters now: the DM
-- compliance build gets its own project, and the lagoon database is never to be
-- touched. This file is what makes a fresh project possible.
--
-- WHERE THE COLUMNS COME FROM. Reconstructed from the authoritative uses in the
-- code, not invented:
--   * the `readings` column list documented in db/queries.py's module docstring
--   * the row built by insert_reading()      (db/queries.py:169-177)
--   * the row built by insert_prediction()   (db/queries.py:210-216)
--   * the columns written by validate_open_predictions() (db/queries.py:256-261)
--   * the constraint names db/schema.sql drops BY NAME (schema.sql:31,46) —
--     these must match exactly or the SaaS migration silently leaves the old
--     single-site constraint in place, and two organisations then collide on
--     (site_name, year, month).
--
-- Types are DOUBLE PRECISION to match `sites.volume_m3` in schema.sql and the
-- floats the Python layer sends. No RLS here: schema_rls.sql enables it on both
-- tables and defines the policies, which is the correct place for it.

-- ── Refuse to run against a database that already has these tables ───────────
-- This is the guard against the one irreversible mistake available here: pasting
-- the LAGOON project's credentials into a fresh-bootstrap run. That database has
-- both tables and years of production readings in them. A fresh project has
-- neither. IF NOT EXISTS would silently no-op and let the rest of the bootstrap
-- proceed against live client data — so this aborts loudly instead.
--
-- If you are deliberately re-running the bootstrap on a half-built project, drop
-- the two tables first and you will get this file's intent rather than a merge.
DO $$
BEGIN
    IF to_regclass('public.readings') IS NOT NULL
       OR to_regclass('public.predictions') IS NOT NULL THEN
        RAISE EXCEPTION
            'readings and/or predictions already exist — this is not a fresh '
            'database. If you meant to bootstrap a NEW project, you are almost '
            'certainly connected to the wrong one: check SUPABASE_URL against '
            'the lagoon project before going further.';
    END IF;
END $$;

-- ── readings ─────────────────────────────────────────────────────────────────
-- One aggregated monthly record per site. 016 is explicit that this table is
-- left untouched by the lab-sample work, so the monthly dashboard keeps its
-- existing shape; it is reproduced here exactly as it was, not modernised.
CREATE TABLE public.readings (
    id                  BIGSERIAL PRIMARY KEY,
    site_name           TEXT NOT NULL,
    year                INTEGER NOT NULL,
    month               INTEGER NOT NULL,
    submitted_at        TIMESTAMPTZ DEFAULT now(),

    ph                  DOUBLE PRECISION,
    do_mgl              DOUBLE PRECISION,
    tss_mgl             DOUBLE PRECISION,
    turbidity_ntu       DOUBLE PRECISION,
    cod_mgl             DOUBLE PRECISION,
    ammonia_mgl         DOUBLE PRECISION,
    phosphate_mgl       DOUBLE PRECISION,
    oil_grease_mgl      DOUBLE PRECISION,
    ecoli_cfu           DOUBLE PRECISION,
    total_coliforms_cfu DOUBLE PRECISION,
    chla_ugl            DOUBLE PRECISION,
    phycocyanin_ugl     DOUBLE PRECISION,
    salinity_psu        DOUBLE PRECISION,
    water_temp_c        DOUBLE PRECISION,

    -- Named implicitly as readings_site_name_year_month_key, which is the name
    -- schema.sql:31 drops. Do not rename it.
    UNIQUE (site_name, year, month)
);

ALTER TABLE public.readings
    ADD CONSTRAINT readings_month_check CHECK (month BETWEEN 1 AND 12);

COMMENT ON TABLE public.readings IS
    'Aggregated monthly water readings, one row per site-month. Predates the '
    'multi-tenant work: schema.sql adds site_id and swaps the uniqueness key to '
    '(site_id, year, month). Reconstructed in migration 000 because the original '
    'DDL was never in the repository.';

-- ── predictions ──────────────────────────────────────────────────────────────
-- The forward-validation ledger: a prediction is recorded before the month's
-- reading exists, then validated against the actual when it arrives. That
-- before-the-fact ordering is what makes the science layer's track record
-- meaningful rather than a retrospective fit, so `actual` and everything derived
-- from it are deliberately nullable — a row with actual IS NULL is an open
-- prediction, and db/queries.py:238 selects exactly on that.
CREATE TABLE public.predictions (
    id             BIGSERIAL PRIMARY KEY,
    site_name      TEXT NOT NULL,
    year           INTEGER NOT NULL,
    month          INTEGER NOT NULL,
    parameter      TEXT NOT NULL,

    predicted      DOUBLE PRECISION NOT NULL,
    band_low       DOUBLE PRECISION,
    band_high      DOUBLE PRECISION,
    confidence_pct DOUBLE PRECISION,

    actual         DOUBLE PRECISION,   -- NULL = still open
    within_band    BOOLEAN,
    abs_error      DOUBLE PRECISION,
    pct_error      DOUBLE PRECISION,
    validated_at   TIMESTAMPTZ,

    created_at     TIMESTAMPTZ DEFAULT now(),

    -- Named implicitly as predictions_site_name_year_month_parameter_key, the
    -- name schema.sql:46 drops. Do not rename it.
    UNIQUE (site_name, year, month, parameter)
);

ALTER TABLE public.predictions
    ADD CONSTRAINT predictions_month_check CHECK (month BETWEEN 1 AND 12);

COMMENT ON TABLE public.predictions IS
    'Forward-prediction ledger. A row is written BEFORE the actual is known and '
    'validated afterwards; actual IS NULL means still open. Reconstructed in '
    'migration 000 — the original DDL was never in the repository.';

-- ── deployment_identity ──────────────────────────────────────────────────────
-- One row naming which deployment this database IS. It exists so that tooling
-- can refuse to write to the wrong one.
--
-- The standing rule for this build is that the DM compliance product gets its
-- own database and the lagoon database is never touched. Nothing enforced that:
-- both projects answer to the same SUPABASE_URL/SUPABASE_KEY pair, the client
-- code is identical because one repo was copied from the other, and the failure
-- is silent and irreversible — a seeder or migration writing into live client
-- data. A marker row turns that into a refusal.
--
-- The lagoon database will never carry a row saying 'dm-tech-apps', because this
-- file cannot run there: the guard above aborts on its existing `readings`.
CREATE TABLE public.deployment_identity (
    -- Single-row table: the CHECK on a BOOLEAN primary key permits exactly one
    -- row, so there can never be two answers to "which database is this".
    id         BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    deployment TEXT NOT NULL,
    note       TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO public.deployment_identity (deployment, note)
VALUES (
    'dm-tech-apps',
    'DM compliance build. Distinct from the DECCA lagoon database, which is a '
    'frozen rollback point and must never be written to by this codebase.'
);

ALTER TABLE public.deployment_identity ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.deployment_identity TO service_role;

-- Readable by any authenticated user — it names the deployment, not a secret.
-- No mutate policy at all: identity is set once, at bootstrap, and only the
-- service role (which bypasses RLS) can change it. A tenant admin renaming the
-- deployment would disarm every guard built on it.
DROP POLICY IF EXISTS select_deployment_identity ON public.deployment_identity;
CREATE POLICY select_deployment_identity ON public.deployment_identity
  FOR SELECT TO authenticated USING (true);

COMMENT ON TABLE public.deployment_identity IS
    'Names which deployment this database is, so tooling can refuse to write to '
    'the wrong one. Exactly one row. Read by db/guard.py.';

COMMIT;
