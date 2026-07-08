# Payments — provider abstraction

All payment logic lives behind the `PaymentProvider` interface (`base.py`).
The rest of the app — `billing.py` facade, `/billing/*` endpoints, the React
frontend — never references a specific provider.

## Switching providers (no code changes)

```toml
# .streamlit/secrets.toml
[payments]
provider = "checkout"   # or "stripe"
```

or `PAYMENT_PROVIDER=checkout|stripe` as an environment variable (env var
wins). Default: `checkout`.

## Providers

| Capability              | Checkout.com (`checkout`, active)                      | Stripe (`stripe`, kept intact, disabled)   |
|-------------------------|--------------------------------------------------------|--------------------------------------------|
| Customer creation       | `POST /customers`                                      | `stripe.Customer`                           |
| Subscription creation   | Hosted Payments Page, recurring series first payment   | Stripe Checkout (subscription mode)         |
| Recurring billing       | Merchant-initiated — `run_recurring_billing.py` daily  | Automatic (Stripe subscriptions)            |
| Webhooks                | `cko-signature` HMAC-SHA256                            | `stripe-signature` (SDK verification)       |
| Cancellation            | `POST /billing/cancel` (clears stored source)          | Portal or `POST /billing/cancel`            |
| Payment status          | `subscription_status` column via webhooks              | Stripe subscription status                  |
| Hosted billing portal   | — (frontend shows Cancel Subscription instead)         | Stripe Customer Portal                      |

## Setup (same flow as the original Stripe setup)

1. Run the migration `db/migrations/002_payment_provider.sql` in Supabase.
2. `python create_checkout_webhook.py` — validates the key, registers the
   webhook, writes `[checkout]` + `[payments]` to secrets.toml.
   (Stripe equivalents: `create_stripe_products.py`, `create_stripe_webhook.py`.)
3. Schedule `python run_recurring_billing.py` daily (Render Cron Job).

Orgs that subscribed via Stripe keep routing cancellations/status checks to
Stripe (`payment_provider` column) even while Checkout.com is active for new
checkouts.
