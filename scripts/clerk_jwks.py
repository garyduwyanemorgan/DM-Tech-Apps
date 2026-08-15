#!/usr/bin/env python3
"""Teach the self-hosted Supabase stack to accept Clerk-signed JWTs.

WHAT THIS SOLVES

PostgREST validates one `jwt-secret`. The stack ships it the 40-character
symmetric JWT_SECRET, which is what signs the anon and service_role keys — so
PostgREST accepts those two and nothing else. Clerk signs session tokens with
RS256 against a per-instance public key set. Pointing PostgREST at Clerk's JWKS
instead would accept Clerk users and immediately break anon and service_role,
which is every existing caller including db/client.py.

A JWKS holds MANY keys, and PostgREST tries each. So the fix is one key set
containing both: Clerk's RS256 public keys, plus the local HS256 secret encoded
as an `oct` key. Nothing is weakened — the same secret validates the same
tokens; it is simply expressed as JWK rather than as a bare string.

    docker-compose.yml already reads it:
        PGRST_JWT_SECRET: ${JWT_JWKS:-${JWT_SECRET}}

so this writes JWT_JWKS into the stack's .env and the compose file needs no edit.

USAGE

    python scripts/clerk_jwks.py --verify
    python scripts/clerk_jwks.py --domain <slug>.clerk.accounts.dev
    python scripts/clerk_jwks.py --publishable-key pk_test_…
    python scripts/clerk_jwks.py --local-only

--local-only writes a key set holding just the HS256 key. That is behaviourally
identical to the default configuration and exists to prove the mechanism before
Clerk is involved.

After writing, apply it:

    cd C:/AI/supabase/docker && docker compose up -d rest

WHAT THIS DOES NOT DO

It does not make Clerk tokens WORK — only accepted as validly signed. PostgREST
reads the database role from the token's `role` claim, and a stock Clerk session
token has no such claim, so the caller stays `anon` and every policy fails
closed. The `role: authenticated` claim must be added in the Clerk dashboard
under Sessions -> customize session token. That is not expressible here.

Nor does it touch GoTrue, Storage or Realtime, which keep verifying the
symmetric secret directly. They are unaffected either way: Clerk users do not
authenticate through GoTrue.
"""
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

DOCKER_ENV = Path(r"C:\AI\supabase\docker\.env")
LOCAL_KID = "supabase-local-hs256"


def _fail(message: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def domain_from_publishable_key(key: str) -> str:
    """Clerk encodes the instance's frontend API domain in the publishable key.

    `pk_test_<base64>` / `pk_live_<base64>`, where the decoded value is the
    domain with a trailing `$`. This mirrors api_server.py's
    _clerk_frontend_api_domain() rather than inventing a second derivation — the
    two must agree, or the backend would verify tokens against one instance's
    JWKS while the database trusted another's.
    """
    parts = key.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != "pk":
        _fail(f"not a Clerk publishable key: {key[:12]}…")
    try:
        decoded = base64.b64decode(parts[2] + "==").decode()
    except Exception as exc:
        _fail(f"could not decode the publishable key: {exc}")
    return decoded.rstrip("$")


def fetch_clerk_keys(domain: str) -> list[dict]:
    url = f"https://{domain}/.well-known/jwks.json"
    print(f"  fetching {url}")
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.load(response)
    except Exception as exc:
        _fail(f"could not fetch Clerk's JWKS: {type(exc).__name__}: {exc}")
    keys = payload.get("keys") or []
    if not keys:
        _fail(f"{url} returned no keys — is {domain} the right instance?")
    for key in keys:
        if key.get("kty") != "RSA":
            _fail(f"unexpected key type {key.get('kty')!r} from Clerk")
        key.setdefault("use", "sig")
    print(f"  got {len(keys)} Clerk key(s): {[k.get('kid') for k in keys]}")
    return keys


def _read_env(path: Path) -> list[str]:
    if not path.is_file():
        _fail(f"{path} not found — is the Supabase stack checked out there?")
    return path.read_text(encoding="utf-8").splitlines()


def _value(lines: list[str], name: str) -> str | None:
    for line in lines:
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return None


def local_hs256_key(lines: list[str]) -> dict:
    secret = _value(lines, "JWT_SECRET")
    if not secret:
        _fail("JWT_SECRET is not set in the stack's .env")
    return {
        "kty": "oct",
        "k": base64.urlsafe_b64encode(secret.encode()).decode().rstrip("="),
        "alg": "HS256",
        "kid": LOCAL_KID,
        "use": "sig",
    }


def verify(lines: list[str]) -> int:
    """Report what PostgREST will trust. Never prints key material."""
    raw = _value(lines, "JWT_JWKS")
    if not raw:
        print("JWT_JWKS is empty -> PostgREST falls back to the bare JWT_SECRET.")
        print("Only anon and service_role are accepted. Clerk tokens are rejected.")
        return 1
    try:
        keys = json.loads(raw).get("keys", [])
    except json.JSONDecodeError as exc:
        _fail(f"JWT_JWKS is set but is not valid JSON: {exc}")
    print(f"JWT_JWKS holds {len(keys)} key(s):")
    for key in keys:
        kind = "local HS256" if key.get("kty") == "oct" else "Clerk RS256"
        print(f"  - {key.get('kid')}  {key.get('kty')}/{key.get('alg')}  ({kind})")
    has_local = any(k.get("kty") == "oct" for k in keys)
    has_clerk = any(k.get("kty") == "RSA" for k in keys)
    if not has_local:
        print("\nWARNING: no symmetric key. anon and service_role will be REJECTED,")
        print("which breaks db/client.py and every existing caller.")
        return 1
    if not has_clerk:
        print("\nNo Clerk keys yet — Clerk tokens will be rejected.")
        return 1
    print("\nBoth key kinds present. Remaining step is Clerk-side: the session")
    print('token must carry "role": "authenticated" or callers stay anon.')
    return 0


def write(lines: list[str], keys: list[dict], path: Path) -> None:
    blob = json.dumps({"keys": keys}, separators=(",", ":"))
    if "\n" in blob:
        _fail("refusing to write a multi-line value into .env")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(f".backup-{stamp}")
    shutil.copy2(path, backup)
    print(f"  backed up {path.name} -> {backup.name}")

    out, replaced = [], False
    for line in lines:
        if line.startswith("JWT_JWKS="):
            out.append("JWT_JWKS=" + blob)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append("JWT_JWKS=" + blob)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")

    kinds = [f"{k.get('kid')} ({k.get('kty')})" for k in keys]
    print(f"  wrote JWT_JWKS with {len(keys)} key(s): {', '.join(kinds)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--domain", help="Clerk frontend API domain")
    group.add_argument("--publishable-key", help="pk_test_… / pk_live_…")
    group.add_argument("--local-only", action="store_true",
                       help="write only the HS256 key (no Clerk)")
    group.add_argument("--verify", action="store_true",
                       help="report what is configured; change nothing")
    parser.add_argument("--env", type=Path, default=DOCKER_ENV,
                        help=f"stack .env (default {DOCKER_ENV})")
    args = parser.parse_args()

    lines = _read_env(args.env)

    if args.verify:
        return verify(lines)

    keys = [local_hs256_key(lines)]
    if not args.local_only:
        domain = args.domain or domain_from_publishable_key(args.publishable_key)
        print(f"  Clerk instance: {domain}")
        keys = fetch_clerk_keys(domain) + keys

    write(lines, keys, args.env)
    print("\nNow apply it:")
    print("  cd C:/AI/supabase/docker && docker compose up -d rest")
    print("Then re-check with: python scripts/clerk_jwks.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
