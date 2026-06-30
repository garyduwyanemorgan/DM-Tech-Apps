#!/usr/bin/env python3
"""
Create Stripe Products and Prices for DECCA Lagoons Dashboard SaaS.
Updates .streamlit/secrets.toml with the newly created Price IDs.
"""

import os
import re
import sys
import pathlib

# Ensure we can import stripe
try:
    import stripe
except ImportError:
    print("Error: stripe package not found. Please install it using: pip install stripe")
    sys.exit(1)


# Plan details
PLANS = {
    "starter": {
        "name": "Starter Plan",
        "price_usd": 199,
        "description": "1 lagoon site — ideal for single-property operators",
    },
    "growth": {
        "name": "Growth Plan",
        "price_usd": 799,
        "description": "Up to 5 lagoon sites — small portfolio managers",
    },
    "professional": {
        "name": "Professional Plan",
        "price_usd": 1999,
        "description": "Up to 15 lagoon sites — consultants and large portfolios",
    }
}


def read_secret_key_from_toml(filepath: pathlib.Path) -> str:
    if not filepath.exists():
        return ""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Look for secret_key under [stripe]
        stripe_match = re.search(r"\[stripe\](.*?)(?=\n\[|$)", content, re.DOTALL)
        if stripe_match:
            key_match = re.search(r'secret_key\s*=\s*"([^"]*)"', stripe_match.group(1))
            if key_match:
                return key_match.group(1).strip()
    except Exception as e:
        print(f"Warning reading secrets.toml: {e}")
    return ""


def update_secrets_toml(filepath: pathlib.Path, secret_key: str, prices: dict):
    if not filepath.exists():
        # Create directory if it doesn't exist
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Streamlit secrets file\n")

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    stripe_section = False
    stripe_section_found = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[stripe]"):
            stripe_section = True
            stripe_section_found = True
        elif stripped.startswith("[") and not stripped.startswith("[stripe]"):
            stripe_section = False

        if stripe_section:
            if stripped.startswith("secret_key"):
                line = re.sub(r'(secret_key\s*=\s*)"[^"]*"', f'\\1"{secret_key}"', line)
            elif stripped.startswith("price_starter"):
                line = re.sub(r'(price_starter\s*=\s*)"[^"]*"', f'\\1"{prices["starter"]}"', line)
            elif stripped.startswith("price_growth"):
                line = re.sub(r'(price_growth\s*=\s*)"[^"]*"', f'\\1"{prices["growth"]}"', line)
            elif stripped.startswith("price_professional"):
                line = re.sub(r'(price_professional\s*=\s*)"[^"]*"', f'\\1"{prices["professional"]}"', line)
        new_lines.append(line)

    # If [stripe] section wasn't present at all, append it
    if not stripe_section_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append("\n[stripe]\n")
        new_lines.append(f'secret_key      = "{secret_key}"\n')
        new_lines.append('webhook_secret  = ""\n')
        new_lines.append(f'price_starter      = "{prices["starter"]}"\n')
        new_lines.append(f'price_growth       = "{prices["growth"]}"\n')
        new_lines.append(f'price_professional = "{prices["professional"]}"\n')

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    print("=" * 60)
    print("      DECCA SaaS Stripe Live Product Setup Assistant")
    print("=" * 60)

    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"

    # Step 1: Get Stripe Secret Key
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret_key:
        secret_key = read_secret_key_from_toml(secrets_path)

    if not secret_key:
        print("Please enter your Stripe Live or Test Secret Key (e.g. sk_live_... or sk_test_...):")
        secret_key = input("> ").strip()
        if not secret_key:
            print("Error: Stripe Secret Key is required to create products.")
            sys.exit(1)

    stripe.api_key = secret_key

    # Validate Stripe Secret Key by retrieving account details
    try:
        print("\nVerifying Stripe connection...")
        account = stripe.Account.retrieve()
        print(f"Connected successfully to Stripe Account: {account.id}")
        mode = "live" if secret_key.startswith("sk_live") else "test"
        print(f"Environment Mode: {mode.upper()}")
    except Exception as e:
        print(f"Error connecting to Stripe API: {e}")
        print("Please verify your secret key and internet connection.")
        sys.exit(1)

    # Step 2: Create Products and Prices
    price_ids = {}
    print("\nCreating Products and Prices on Stripe...")
    
    for plan_key, plan_info in PLANS.items():
        try:
            print(f"- Creating {plan_info['name']} (${plan_info['price_usd']}/mo)...")
            product = stripe.Product.create(
                name=f"DECCA - {plan_info['name']}",
                description=plan_info['description'],
                metadata={"plan_key": plan_key}
            )
            price = stripe.Price.create(
                product=product.id,
                unit_amount=plan_info['price_usd'] * 100, # In cents
                currency="usd",
                recurring={"interval": "month"},
                metadata={"plan_key": plan_key}
            )
            price_ids[plan_key] = price.id
            print(f"  [OK] Success! Price ID: {price.id}")
        except Exception as e:
            print(f"  [ERROR] Failed to create {plan_info['name']}: {e}")
            sys.exit(1)

    # Step 3: Update secrets.toml
    print(f"\nWriting Price IDs to {secrets_path.relative_to(pathlib.Path.cwd())}...")
    try:
        update_secrets_toml(secrets_path, secret_key, price_ids)
        print("[OK] secrets.toml successfully updated!")
    except Exception as e:
        print(f"[ERROR] Failed to update secrets.toml: {e}")
        print("\nPlease manually add the following Price IDs to your secrets.toml:")
        for plan_key, price_id in price_ids.items():
            print(f"price_{plan_key} = \"{price_id}\"")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("                    SETUP COMPLETE!")
    print("=" * 60)
    print("What to do next:")
    print("1. Set up your Webhook Endpoint in the Stripe Dashboard:")
    print("   - URL: https://<your-api-domain>/api/billing/webhook")
    print("   - Events to listen for:")
    print("     * customer.subscription.created")
    print("     * customer.subscription.updated")
    print("     * customer.subscription.deleted")
    print("     * checkout.session.completed")
    print("2. Obtain the Webhook Signing Secret (starts with whsec_...)")
    print("3. Add the Webhook Signing Secret to secrets.toml under 'webhook_secret'")
    print("=" * 60)


if __name__ == "__main__":
    main()
