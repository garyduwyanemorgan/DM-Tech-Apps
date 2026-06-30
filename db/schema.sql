-- ── Database Migration: SaaS Phase 1 ──
-- Run this in your Supabase SQL editor to enable multi-tenancy.

-- 1. Create organizations table
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Create sites table (dynamic sites linked to organizations)
CREATE TABLE IF NOT EXISTS sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    volume_m3 DOUBLE PRECISION DEFAULT 0.0,
    salinity_baseline DOUBLE PRECISION DEFAULT 45.0,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(organization_id, name)
);

-- 3. Add site_id to readings (referencing sites.id)
ALTER TABLE readings ADD COLUMN IF NOT EXISTS site_id UUID REFERENCES sites(id) ON DELETE CASCADE;

-- Update unique constraint for readings
-- Note: In PostgreSQL/Supabase, constraints are named. To prevent unique conflicts,
-- we check if the site_id constraint exists, and replace the old site_name constraint.
DO $$
BEGIN
    -- Drop the old constraint (if it exists) that restricted site_name + year + month
    ALTER TABLE readings DROP CONSTRAINT IF EXISTS readings_site_name_year_month_key;
    
    -- Add the new constraint on site_id + year + month
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'readings_site_id_year_month_key'
    ) THEN
        ALTER TABLE readings ADD CONSTRAINT readings_site_id_year_month_key UNIQUE(site_id, year, month);
    END IF;
END $$;

-- 4. Add site_id to predictions (referencing sites.id)
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS site_id UUID REFERENCES sites(id) ON DELETE CASCADE;

DO $$
BEGIN
    ALTER TABLE predictions DROP CONSTRAINT IF EXISTS predictions_site_name_year_month_parameter_key;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'predictions_site_id_year_month_parameter_key'
    ) THEN
        ALTER TABLE predictions ADD CONSTRAINT predictions_site_id_year_month_parameter_key UNIQUE(site_id, year, month, parameter);
    END IF;
END $$;
