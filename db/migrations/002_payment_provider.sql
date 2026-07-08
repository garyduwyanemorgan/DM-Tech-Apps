-- Run this in the Supabase SQL editor (Project → SQL Editor → New query)
-- Adds provider-agnostic payment columns to the organizations table.
-- The legacy stripe_* columns are kept intact so Stripe can be re-enabled
-- by configuration (PAYMENT_PROVIDER=stripe) without another migration.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS payment_provider        text,
  ADD COLUMN IF NOT EXISTS payment_customer_id     text,
  ADD COLUMN IF NOT EXISTS payment_subscription_id text,
  ADD COLUMN IF NOT EXISTS payment_source_id       text,
  ADD COLUMN IF NOT EXISTS subscription_status     text,
  ADD COLUMN IF NOT EXISTS next_billing_at         timestamptz;

-- Tag orgs that already subscribed through Stripe so cancellations/status
-- checks keep routing to Stripe. Subscription state itself stays in the
-- stripe_* columns, which remain the source of truth for those orgs.
UPDATE organizations
SET payment_provider    = 'stripe',
    payment_customer_id = stripe_customer_id
WHERE stripe_customer_id IS NOT NULL
  AND payment_provider IS NULL;
