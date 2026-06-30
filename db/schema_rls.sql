-- ── Database Migration: SaaS Phase 2 (Row-Level Security) ──
-- Run this in your Supabase SQL editor to secure your tables.

-- 1. Create user profiles table
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES public.organizations(id) ON DELETE SET NULL,
    role TEXT CHECK (role IN ('super_admin', 'admin', 'operator', 'auditor')) DEFAULT 'operator',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS on user_profiles
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- 2. Auth signup trigger helper
-- Automatically create a user_profiles record when a user signs up in auth.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.user_profiles (id, role)
  VALUES (new.id, 'operator');
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger definition
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 3. Security context helper functions
CREATE OR REPLACE FUNCTION public.get_user_organization()
RETURNS UUID SECURITY DEFINER AS $$
BEGIN
  RETURN (
    SELECT organization_id 
    FROM public.user_profiles 
    WHERE id = auth.uid()
  );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION public.get_user_role()
RETURNS TEXT SECURITY DEFINER AS $$
BEGIN
  RETURN (
    SELECT role 
    FROM public.user_profiles 
    WHERE id = auth.uid()
  );
END;
$$ LANGUAGE plpgsql;

-- 4. Enable RLS on core tables
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.readings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;

-- 5. Row-Level Security Policies

-- ── Organizations table policies ──
DROP POLICY IF EXISTS select_org ON public.organizations;
CREATE POLICY select_org ON public.organizations 
  FOR SELECT USING (
    id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_org ON public.organizations;
CREATE POLICY mutate_org ON public.organizations 
  FOR ALL USING (
    public.get_user_role() = 'super_admin'
  );

-- ── Sites table policies ──
DROP POLICY IF EXISTS select_sites ON public.sites;
CREATE POLICY select_sites ON public.sites 
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_sites ON public.sites;
CREATE POLICY mutate_sites ON public.sites 
  FOR ALL USING (
    (organization_id = public.get_user_organization() AND public.get_user_role() IN ('admin', 'super_admin'))
  );

-- ── Readings table policies ──
DROP POLICY IF EXISTS select_readings ON public.readings;
CREATE POLICY select_readings ON public.readings 
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_readings ON public.readings;
CREATE POLICY mutate_readings ON public.readings 
  FOR ALL USING (
    (site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
     AND public.get_user_role() IN ('admin', 'operator', 'super_admin'))
  );

-- ── Predictions table policies ──
DROP POLICY IF EXISTS select_predictions ON public.predictions;
CREATE POLICY select_predictions ON public.predictions 
  FOR SELECT USING (
    site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_predictions ON public.predictions;
CREATE POLICY mutate_predictions ON public.predictions 
  FOR ALL USING (
    (site_id IN (SELECT id FROM public.sites WHERE organization_id = public.get_user_organization())
     AND public.get_user_role() IN ('admin', 'operator', 'super_admin'))
  );

-- ── User Profiles table policies ──
DROP POLICY IF EXISTS select_profiles ON public.user_profiles;
CREATE POLICY select_profiles ON public.user_profiles 
  FOR SELECT USING (
    organization_id = public.get_user_organization() OR id = auth.uid() OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_profiles ON public.user_profiles;
CREATE POLICY mutate_profiles ON public.user_profiles 
  FOR ALL USING (
    (organization_id = public.get_user_organization() AND public.get_user_role() IN ('admin', 'super_admin'))
  );
