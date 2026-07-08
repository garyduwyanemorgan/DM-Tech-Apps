#!/usr/bin/env python3
"""
Set up Checkout.com for Dubai Lagoons Dashboard SaaS.

Mirrors the Stripe setup flow (create_stripe_products.py /
create_stripe_webhook.py). Checkout.com needs no product/price objects —
plan amounts are sent per payment from billing.PLANS — so this single script:

  1. Validates the Checkout.com secret key
  2. Registers the webhook endpoint (payment_approved / payment_captured /
     payment_declined / payment_refunded → /billing/webhook)
  3. Writes the [checkout] and [payments] blocks to .streamlit/secrets.toml

Run:  python create_checkout_webhook.py
"""

import os
import re
import sys
import pathlib

try:
    import httpx
except ImportError:
    print("Error: httpx package not found. Please install it using: pip install httpx")
    sys.exit(1)

from payments.checkout_provider import API_LIVE, API_SANDBOX, WEBHOOK_EVENTS

BASE_URL = "https://lagoons.gdm-enviro.com"


def read_key_from_toml(filepath: pathlib.Path, section: str, key: str) -> str:
    if not filepath.exists():
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        section_match = re.search(rf"\[{section}\](.*?)(?=\n\[|$)", content, re.DOTALL)
        if section_match:
            key_match = re.search(rf'{key}\s*=\s*"([^"]*)"', section_match.group(1))
            if key_match:
                return key_match.group(1).strip()
    except Exception as e:
        print(f"Warning reading secrets.toml: {e}")
    return ""


def upsert_toml_section(filepath: pathlib.Path, section: str, values: dict):
    """Update keys inside [section], appending the section if missing."""
    if not filepath.exists():
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Streamlit secrets file\n")

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    in_section = False
    section_found = False
    remaining = dict(values)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"[{section}]"):
            in_section = True
            section_found = True
        elif stripped.startswith("["):
            # Leaving the section — append any keys not already present
            if in_section and remaining:
                for k, v in remaining.items():
                    new_lines.append(f'{k} = "{v}"\n')
                remaining = {}
            in_section = False

        if in_section:
            for k in list(remaining):
                if stripped.startswith(k):
                    line = re.sub(rf'({k}\s*=\s*)"[^"]*"', f'\\1"{remaining.pop(k)}"', line)
                    break
        new_lines.append(line)

    if in_section and remaining:
        for k, v in remaining.items():
            new_lines.append(f'{k} = "{v}"\n')
        remaining = {}

    if not section_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"\n[{section}]\n")
        for k, v in values.items():
            new_lines.append(f'{k} = "{v}"\n')

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    print("=" * 60)
    print("     Compliance SaaS Checkout.com Setup Assistant")
    print("=" * 60)

    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"

    # Step 1: Get Checkout.com Secret Key
    secret_key = os.environ.get("CHECKOUT_SECRET_KEY", "")
    if not secret_key:
        secret_key = read_key_from_toml(secrets_path, "checkout", "secret_key")

    if not secret_key:
        print("Please enter your Checkout.com Secret Key (sk_... or sk_sbox_... for sandbox):")
        secret_key = input("> ").strip()
        if not secret_key:
            print("Error: Checkout.com Secret Key is required.")
            sys.exit(1)

    api_base = API_SANDBOX if "sbox" in secret_key else API_LIVE
    mode = "SANDBOX" if "sbox" in secret_key else "LIVE"
    headers = {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}

    # Step 2: Validate the key by listing existing webhooks
    print(f"\nVerifying Checkout.com connection ({mode})...")
    try:
        resp = httpx.get(f"{api_base}/webhooks", headers=headers, timeout=30.0)
    except Exception as e:
        print(f"Error connecting to Checkout.com API: {e}")
        sys.exit(1)
    if resp.status_code in (401, 403):
        print("Error: Checkout.com rejected the secret key. Verify it and try again.")
        sys.exit(1)
    if resp.status_code not in (200, 204):
        print(f"Error: unexpected response from Checkout.com: HTTP {resp.status_code}")
        sys.exit(1)
    print("Connected successfully to Checkout.com.")

    # Step 3: Register the webhook endpoint.
    # The API app is mounted under /api on the unified FastAPI server, so the
    # public webhook path is /api/billing/webhook (the bare /billing/webhook
    # path is swallowed by the React catchall route).
    webhook_url = f"{BASE_URL.rstrip('/')}/api/billing/webhook"
    print(f"\nRegistering Webhook URL: {webhook_url}")
    try:
        resp = httpx.post(f"{api_base}/webhooks", headers=headers, timeout=30.0, json={
            "url": webhook_url,
            "active": True,
            "content_type": "json",
            "event_types": WEBHOOK_EVENTS,
        })
    except Exception as e:
        print(f"  [ERROR] Failed to create Webhook Endpoint: {e}")
        sys.exit(1)
    if resp.status_code not in (200, 201):
        print(f"  [ERROR] Failed to create Webhook Endpoint: HTTP {resp.status_code} {resp.text}")
        sys.exit(1)
    webhook = resp.json()
    print(f"  [OK] Success! Webhook Endpoint ID: {webhook.get('id')}")

    # Classic Checkout.com webhooks sign payloads (cko-signature header) with
    # the account secret key unless a dedicated signature key is configured in
    # the Dashboard. If you set one there, update webhook_secret to match.
    webhook_secret = secret_key

    # Step 4: Write secrets.toml — [checkout] credentials + activate the provider
    print(f"\nWriting configuration to {secrets_path}...")
    upsert_toml_section(secrets_path, "checkout", {
        "secret_key":      secret_key,
        "webhook_secret":  webhook_secret,
        "billing_country": read_key_from_toml(secrets_path, "checkout", "billing_country") or "AE",
    })
    upsert_toml_section(secrets_path, "payments", {"provider": "checkout"})
    print("[OK] secrets.toml successfully updated!")

    print("\n" + "=" * 60)
    print("                    SETUP COMPLETE!")
    print("=" * 60)
    print("What to do next:")
    print("1. Recurring billing is merchant-initiated with Checkout.com —")
    print("   schedule this to run daily (e.g. Render Cron Job):")
    print("     python run_recurring_billing.py")
    print("2. If you configured a dedicated webhook signature key in the")
    print("   Checkout.com Dashboard, set it as webhook_secret in secrets.toml.")
    print("3. To switch back to Stripe at any time, set:")
    print('     [payments] provider = "stripe"   (or PAYMENT_PROVIDER=stripe)')
    print("=" * 60)


if __name__ == "__main__":
    main()
