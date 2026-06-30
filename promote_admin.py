"""
Promote a user to super_admin.

Usage:
    set SUPABASE_URL=https://aahekvsznsceqkmtcnhl.supabase.co
    set SUPABASE_KEY=<your-service-role-key>
    python promote_admin.py --email your@email.com

The service role key is in your Supabase dashboard:
  Project Settings -> API -> service_role (secret key)
"""
import os
import sys
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="Email of the user to promote")
    parser.add_argument("--role", default="super_admin", choices=["super_admin", "admin", "operator"])
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL", "https://aahekvsznsceqkmtcnhl.supabase.co")
    key = os.environ.get("SUPABASE_KEY")

    if not key:
        print("ERROR: Set SUPABASE_KEY to your service role key before running.")
        print("  Windows:  set SUPABASE_KEY=eyJhbGci...")
        print("  Mac/Linux: export SUPABASE_KEY=eyJhbGci...")
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase-py not installed. Run: pip install supabase")
        sys.exit(1)

    client = create_client(url, key)

    # Find user by email in auth.users (requires service role)
    print(f"Looking up user: {args.email}")
    try:
        res = client.auth.admin.list_users()
        user = next((u for u in res if getattr(u, 'email', None) == args.email), None)
        if not user:
            print(f"ERROR: No user found with email '{args.email}'")
            print("Users in system:", [getattr(u, 'email', '?') for u in res])
            sys.exit(1)
        user_id = user.id
        print(f"Found user ID: {user_id}")
    except Exception as e:
        print(f"ERROR listing users: {e}")
        sys.exit(1)

    # Check if profile exists
    try:
        existing = client.table("user_profiles").select("*").eq("id", user_id).execute()
        if existing.data:
            # Update role
            client.table("user_profiles").update({"role": args.role}).eq("id", user_id).execute()
            print(f"Updated role to '{args.role}' for {args.email}")
        else:
            # Need org — use first available or create one
            orgs = client.table("organizations").select("id, name").execute()
            if orgs.data:
                org_id = orgs.data[0]["id"]
                org_name = orgs.data[0]["name"]
                print(f"Assigning to org: {org_name}")
            else:
                ins = client.table("organizations").insert({"name": "GDM Enviro"}).execute()
                org_id = ins.data[0]["id"]
                print(f"Created new org: GDM Enviro ({org_id})")

            client.table("user_profiles").insert({
                "id": user_id,
                "organization_id": org_id,
                "role": args.role,
            }).execute()
            print(f"Created profile with role '{args.role}' for {args.email}")

        print(f"\nDone! {args.email} is now '{args.role}'.")
        print("Log out and back in to the dashboard to see the changes.")
    except Exception as e:
        print(f"ERROR updating profile: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
