"""SaaS Tenant Seeding Helper.

Creates a test organization, registers a user in Supabase Auth,
sets up their user profile, and provisions default lagoon sites.
"""
import os
import sys

# Make db/ and core/ importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_client, is_configured
from db.queries import create_organization, create_site

def seed_tenant(email: str, password: str, org_name: str, site_names: list[str]):
    if not is_configured():
        print("Error: Supabase is not configured. Please set SUPABASE_URL and SUPABASE_KEY in your environment.")
        return False
        
    client = get_client()
    try:
        print(f"1. Creating organization '{org_name}'...")
        org_id = create_organization(org_name)
        if not org_id:
            # Check if organization already exists
            res = client.table("organizations").select("id").eq("name", org_name).execute()
            if res.data:
                org_id = res.data[0]["id"]
                print(f"   Organization '{org_name}' already exists (ID: {org_id})")
            else:
                raise Exception("Failed to create organization")
        else:
            print(f"   Created Organization ID: {org_id}")

        print(f"2. Registering user '{email}' in Supabase Auth...")
        try:
            auth_res = client.auth.sign_up({
                "email": email,
                "password": password
            })
            user_id = auth_res.user.id
            print(f"   Registered Auth User ID: {user_id}")
        except Exception as e:
            msg = str(e)
            if "already registered" in msg.lower() or "already exists" in msg.lower() or "unique" in msg.lower():
                print("   User already registered in auth.")
                print("   Note: If the user already exists, they must log in directly with their password.")
                return False
            else:
                raise e

        print("3. Creating user profile record...")
        client.table("user_profiles").insert({
            "id": user_id,
            "organization_id": org_id,
            "role": "admin"
        }).execute()
        print("   User profile created successfully.")

        print("4. Provisioning default lagoon sites...")
        for name in site_names:
            site_id = create_site(org_id, name)
            print(f"   Created Site: {name} (ID: {site_id})")

        print("\nSeeding completed successfully! You can now log into your dashboard using:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        return True

    except Exception as exc:
        print(f"Error during seeding: {exc}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed a test tenant in Supabase")
    parser.add_argument("--email", default="operator@emaar.ae", help="Tenant login email")
    parser.add_argument("--password", default="EmaarPassword123!", help="Tenant login password")
    parser.add_argument("--org", default="Emaar Properties", help="Tenant organization name")
    parser.add_argument("--sites", default="Emaar Lagoon A,Emaar Lagoon B", help="Comma-separated site names")
    
    args = parser.parse_args()
    sites_list = [s.strip() for s in args.sites.split(",") if s.strip()]
    seed_tenant(args.email, args.password, args.org, sites_list)
