#!/usr/bin/env python3
"""
Create Stripe Webhook Endpoint for DECCA Lagoons Dashboard SaaS.
Updates .streamlit/secrets.toml with the newly created Webhook Secret.
"""

import os
import re
import sys
import pathlib

try:
    import stripe
except ImportError:
    print("Error: stripe package not found. Please install it using: pip install stripe")
    sys.exit(1)


def read_secret_key_from_toml(filepath: pathlib.Path) -> str:
    if not filepath.exists():
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        stripe_match = re.search(r"\[stripe\](.*?)(?=\n\[|$)", content, re.DOTALL)
        if stripe_match:
            key_match = re.search(r'secret_key\s*=\s*"([^"]*)"', stripe_match.group(1))
            if key_match:
                return key_match.group(1).strip()
    except Exception as e:
        print(f"Warning reading secrets.toml: {e}")
    return ""


def update_webhook_secret_toml(filepath: pathlib.Path, webhook_secret: str):
    if not filepath.exists():
        print(f"Error: {filepath} does not exist.")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    stripe_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[stripe]"):
            stripe_section = True
        elif stripped.startswith("[") and not stripped.startswith("[stripe]"):
            stripe_section = False

        if stripe_section:
            if stripped.startswith("webhook_secret"):
                line = re.sub(r'(webhook_secret\s*=\s*)"[^"]*"', f'\\1"{webhook_secret}"', line)
        new_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    print("=" * 60)
    print("      DECCA SaaS Stripe Live Webhook Creator")
    print("=" * 60)

    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"

    # Step 1: Get Stripe Secret Key
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret_key:
        secret_key = read_secret_key_from_toml(secrets_path)

    if not secret_key:
        print("Error: Stripe Secret Key not found in secrets.toml or environment variables.")
        sys.exit(1)

    stripe.api_key = secret_key

    # Validate Stripe Secret Key
    try:
        account = stripe.Account.retrieve()
        print(f"Connected to Stripe Account: {account.id}")
    except Exception as e:
        print(f"Error connecting to Stripe API: {e}")
        sys.exit(1)

    # Step 2: Configure Webhook URL
    base_url = "https://lagoons.gdm-enviro.com"
    
    # Since the FastAPI route is /billing/webhook, the endpoint URL should be:
    webhook_url = f"{base_url.rstrip('/')}/billing/webhook"
    print(f"\nRegistering Webhook URL: {webhook_url}")

    # Step 3: Create the Webhook Endpoint
    try:
        webhook = stripe.WebhookEndpoint.create(
            url=webhook_url,
            enabled_events=[
                "customer.subscription.created",
                "customer.subscription.updated",
                "customer.subscription.deleted",
                "checkout.session.completed"
            ],
            description="DECCA Lagoons Dashboard Live Webhook Endpoint"
        )
        print(f"  [OK] Success! Webhook Endpoint ID: {webhook.id}")
        
        # Step 4: Write to secrets.toml
        update_webhook_secret_toml(secrets_path, webhook.secret)
        print("  [OK] Webhook Secret saved to secrets.toml!")
        
    except Exception as e:
        print(f"  [ERROR] Failed to create Webhook Endpoint: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("                WEBHOOK SETUP COMPLETE!")
    print("=" * 60)
    print(f"Webhook URL:    {webhook_url}")
    print(f"Signing Secret: {webhook.secret}")
    print("=" * 60)


if __name__ == "__main__":
    main()
