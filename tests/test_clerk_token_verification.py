"""Clerk token verification — what `get_user_from_token` refuses to accept.

Security review finding L4: the decode checked neither `iss` nor `azp`. The JWKS
URL is derived from the configured publishable key, so a token from a *different*
Clerk instance would fail on the signature — but a token minted by another app on
the *same* instance verified perfectly well, and a stolen JWKS-shaped key served
from elsewhere had nothing but the network standing in its way. These tests pin
the two claims that close that:

  1. `iss` must name the instance the publishable key names.
  2. `azp` must sit in CLERK_AUTHORIZED_PARTIES *when that list is configured* —
     and when it is not configured the check is deliberately skipped, because
     locking out every existing deployment is a worse outcome than the low-severity
     replay it prevents. Both halves of that decision are tested.

Style follows tests/test_obligations_api.py: the function under test is called
directly and its collaborators are monkeypatched. No database, no network — the
JWKS cache is populated in-process with a keypair generated here.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

jwt = pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

import api_server  # noqa: E402

# Captured before the autouse fixture stubs it out, so the config-plumbing test
# can still exercise the real env lookup.
_real_authorized_parties = api_server._clerk_authorized_parties

DOMAIN = "clerk.example-tenant.dev"
ISSUER = f"https://{DOMAIN}"
OUR_ORIGIN = "https://app.example-tenant.dev"
SIBLING_ORIGIN = "https://other-app.example-tenant.dev"
KID = "test-kid-1"


def _publishable_key(domain: str) -> str:
    """A pk_test_ key of the shape Clerk issues: base64 of "<domain>$"."""
    b64 = base64.b64encode(f"{domain}$".encode()).decode().rstrip("=")
    return f"pk_test_{b64}"


@pytest.fixture(scope="module")
def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def clerk_instance(monkeypatch, keypair):
    """Pin the instance to DOMAIN and pre-load its JWKS, so no HTTP is attempted."""
    monkeypatch.setattr(api_server, "_clerk_publishable_key", lambda: _publishable_key(DOMAIN))
    jwk = json.loads(RSAAlgorithm.to_jwk(keypair.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(api_server, "_clerk_jwks_cache", {"keys": [jwk]})
    # Default to "not configured" so each test opts in to an allow-list explicitly;
    # a stray CLERK_AUTHORIZED_PARTIES in the developer's .env must not decide these.
    monkeypatch.setattr(api_server, "_clerk_authorized_parties", lambda: set())


def _token(keypair, *, issuer: str = ISSUER, azp: str | None = OUR_ORIGIN, **claims) -> str:
    now = int(time.time())
    payload = {
        "sub": "user_abc123",
        "email": "field.tech@example.com",
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    if azp is not None:
        payload["azp"] = azp
    payload.update(claims)
    return jwt.encode(payload, keypair, algorithm="RS256", headers={"kid": KID})


# ── Derivation: issuer and JWKS URL describe the same instance ────────────────

def test_issuer_and_jwks_url_come_from_the_same_key(keypair):
    assert api_server._clerk_issuer() == ISSUER
    assert api_server._clerk_jwks_url() == f"{ISSUER}/.well-known/jwks.json"


def test_unparseable_key_degrades_to_no_issuer_check(monkeypatch, keypair):
    """A missing/garbled publishable key must not 401 the whole API. We cannot name
    the legitimate issuer, so the issuer check stands down and JWKS remains the
    control — the pre-L4 behaviour, not a new hole."""
    monkeypatch.setattr(api_server, "_clerk_publishable_key", lambda: "")
    assert api_server._clerk_issuer() == ""
    assert api_server.get_user_from_token(_token(keypair, issuer="https://anything.dev")) is not None


# ── The three cases the finding names ────────────────────────────────────────

def test_correct_token_still_passes(keypair):
    user = api_server.get_user_from_token(_token(keypair))
    assert user == {"id": "user_abc123", "email": "field.tech@example.com"}


def test_wrong_issuer_is_rejected(keypair):
    """Same signing key, different instance name — the case JWKS alone cannot see."""
    assert api_server.get_user_from_token(_token(keypair, issuer="https://evil.clerk.accounts.dev")) is None


def test_missing_issuer_is_rejected(keypair):
    token = _token(keypair)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop("iss")
    unsigned = jwt.encode(payload, keypair, algorithm="RS256", headers={"kid": KID})
    assert api_server.get_user_from_token(unsigned) is None


def test_azp_outside_allow_list_is_rejected(monkeypatch, keypair):
    """A sibling app on our own Clerk instance: valid signature, valid issuer."""
    monkeypatch.setattr(api_server, "_clerk_authorized_parties", lambda: {OUR_ORIGIN})
    assert api_server.get_user_from_token(_token(keypair, azp=SIBLING_ORIGIN)) is None


def test_azp_inside_allow_list_passes(monkeypatch, keypair):
    monkeypatch.setattr(api_server, "_clerk_authorized_parties",
                        lambda: {OUR_ORIGIN, "http://localhost:5173"})
    assert api_server.get_user_from_token(_token(keypair))["id"] == "user_abc123"


def test_absent_azp_is_rejected_when_allow_list_configured(monkeypatch, keypair):
    """A configured list that waves through tokens simply lacking the claim would be
    decorative — the claim is the part an attacker's token controls."""
    monkeypatch.setattr(api_server, "_clerk_authorized_parties", lambda: {OUR_ORIGIN})
    assert api_server.get_user_from_token(_token(keypair, azp=None)) is None


def test_absent_azp_passes_when_allow_list_unconfigured(keypair):
    """The documented fail-open: unset CLERK_AUTHORIZED_PARTIES keeps existing
    deployments and fresh local checkouts working. Issuer still applies."""
    assert api_server.get_user_from_token(_token(keypair, azp=None)) is not None


# ── Config plumbing ──────────────────────────────────────────────────────────

def test_allow_list_parsed_from_env(monkeypatch):
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES",
                       f" {OUR_ORIGIN} , http://localhost:5173 ,")
    assert _real_authorized_parties() == {OUR_ORIGIN, "http://localhost:5173"}


def test_expired_token_still_rejected(keypair):
    """Regression guard: the new options dict must not have loosened exp handling."""
    now = int(time.time())
    stale = _token(keypair, iat=now - 4000, nbf=now - 4000, exp=now - 3600)
    assert api_server.get_user_from_token(stale) is None
