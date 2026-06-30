-- ── Database Migration: Clerk Auth Integration ──
-- Decouples user_profiles from Supabase auth.users so Clerk user IDs can be stored.
-- Run in Supabase SQL editor.

-- 1. Drop FK constraint to auth.users (Clerk manages identity now)
ALTER TABLE public.user_profiles DROP CONSTRAINT IF EXISTS user_profiles_id_fkey;

-- 2. Add clerk_id for Clerk user identification (primary lookup key)
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS clerk_id TEXT UNIQUE;

-- 3. Add email for invite-flow matching (links pending profiles to Clerk users on first sign-in)
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS email TEXT;

-- 4. Drop the Supabase auth trigger (Clerk handles signup now)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
