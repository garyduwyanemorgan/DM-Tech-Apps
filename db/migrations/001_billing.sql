-- Run this in the Supabase SQL editor (Project → SQL Editor → New query)
-- Adds billing columns to the organizations table

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS site_limit        integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS plan_name         text    NOT NULL DEFAULT 'starter',
  ADD COLUMN IF NOT EXISTS stripe_customer_id       text,
  ADD COLUMN IF NOT EXISTS stripe_subscription_id   text;

-- Give existing orgs a generous dev limit so nothing breaks immediately
-- Remove or change this before going to production
UPDATE organizations SET site_limit = 999, plan_name = 'dev' WHERE plan_name = 'starter';
