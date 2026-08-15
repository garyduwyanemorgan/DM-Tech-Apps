"""POST /users/invite must not confirm that an address exists in another tenant.

The duplicate check used to be `.eq("email", email)` with no organisation
predicate, so `409 "{email} is already invited or registered."` answered the
question "does this person work for anyone on this platform?" for any admin who
cared to ask. The market is FM contractors bidding against each other, so that
is a competitor staff-list oracle, one probe at a time.

The fix has three halves, and all three are load-bearing:

  1. An *in-org* duplicate keeps the specific message — that is the caller's own
     roster, already readable via GET /users, so it discloses nothing.
  2. A *cross-tenant* duplicate is still refused (get_user_profile's email
     fallback takes `res.data[0]` of a bare email match, so two pending profiles
     with one address would make org assignment on sign-in arbitrary) but the
     wording must not distinguish it from "unknown address".
  3. Clerk's own duplicate-identifier error is the same oracle by another route,
     so it collapses to the same generic refusal instead of surfacing in a 502.

Plus: invite_user emitted no audit event at all — the only user-management
action with no trail — so both the success and the refusal are pinned here.

Style follows tests/test_obligations_api.py: the endpoint function is called
directly with a fake profile and the Supabase client is faked, per
tests/test_site_deletion_tenancy.py. No database, no network, no HTTP layer.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402

ORG = "org-alpha"
RIVAL = "org-beta"
TARGET = "estimator@rival-fm.example"

ADMIN = {"user_id": "clerk_admin", "role": "super_admin", "organization_id": ORG}


# ── fakes ────────────────────────────────────────────────────────────────────

class _Q:
    """A user_profiles query that answers from a fixed list of rows, honouring
    exactly the predicates the endpoint applies."""

    def __init__(self, rows, inserts):
        self.rows, self.inserts, self.filters = rows, inserts, {}
        self.payload = None

    def select(self, *a, **k):
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def execute(self):
        if self.payload is not None:
            self.inserts.append(self.payload)
            return type("R", (), {"data": [self.payload], "count": 1})()
        data = [r for r in self.rows
                if all(r.get(k) == v for k, v in self.filters.items())]
        return type("R", (), {"data": data, "count": len(data)})()


class _Client:
    def __init__(self, rows, inserts):
        self.rows, self.inserts = rows, inserts

    def table(self, name):
        return _Q(self.rows if name == "user_profiles" else [], self.inserts)


class _Request:
    headers = {"origin": "https://app.example"}
    base_url = "https://api.example/"


@pytest.fixture
def env(monkeypatch):
    """Returns (rows, inserts, audits). Mutate `rows` to set up the world."""
    rows: list[dict] = []
    inserts: list[dict] = []
    audits: list[tuple] = []

    import db.client as db_client
    monkeypatch.setattr(db_client, "get_client", lambda *a, **k: _Client(rows, inserts))
    monkeypatch.setattr(api_server, "audit_emit",
                        lambda action, **kw: audits.append((action, kw)))
    # Permission and demo gates are not what this test is about.
    monkeypatch.setattr(api_server, "_ensure_permission", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_create_clerk_invitation",
                        lambda *a, **k: "inv_ok")
    return rows, inserts, audits


def _invite(email=TARGET, role="operator"):
    return api_server.invite_user(
        api_server.InviteRequest(email=email, role=role), _Request(), ADMIN)


# ── the finding ──────────────────────────────────────────────────────────────

def test_cross_tenant_duplicate_does_not_confirm_the_address_exists(env):
    """The whole finding, in one assertion."""
    rows, _, _ = env
    rows.append({"id": "p1", "email": TARGET, "organization_id": RIVAL})
    with pytest.raises(HTTPException) as e:
        _invite()
    assert e.value.status_code == 409
    detail = str(e.value.detail)
    assert TARGET not in detail, (
        f"the refusal echoes the probed address back: {detail!r}. Echoing it "
        "confirms the address is on some tenant's roster.")
    # "cannot be invited" states our decision; the banned words state a fact about
    # the address, which is the disclosure.
    for leak in ("already", "registered", "exists", "another", "organis", "tenant"):
        assert leak not in detail.lower(), (
            f"{detail!r} attributes the refusal ({leak!r}); a competitor can read "
            "the address's status straight off the error.")


def test_cross_tenant_refusal_is_indistinguishable_from_a_clerk_duplicate(env):
    """Two wordings for one condition would be the same oracle by another route."""
    rows, _, _ = env
    rows.append({"id": "p1", "email": TARGET, "organization_id": RIVAL})
    with pytest.raises(HTTPException) as e:
        _invite()
    assert e.value.detail == api_server._INVITE_REFUSED_DETAIL


def test_cross_tenant_duplicate_inserts_nothing(env):
    """It must REFUSE, not insert: get_user_profile links pending profiles on a bare
    email match and takes data[0], so a second pending row makes the invitee's
    organisation on first sign-in arbitrary."""
    rows, inserts, _ = env
    rows.append({"id": "p1", "email": TARGET, "organization_id": RIVAL})
    with pytest.raises(HTTPException):
        _invite()
    assert inserts == [], "a second pending profile for one address was created"


def test_in_org_duplicate_keeps_the_specific_message(env):
    """The caller's own roster is theirs to read; a vague error here is just bad UX."""
    rows, inserts, _ = env
    rows.append({"id": "p1", "email": TARGET, "organization_id": ORG})
    with pytest.raises(HTTPException) as e:
        _invite()
    assert e.value.status_code == 409
    assert TARGET in str(e.value.detail)
    assert "already" in str(e.value.detail).lower()
    assert inserts == []


def test_an_unknown_address_is_still_invited(env):
    """The scoping must not break the endpoint's actual job."""
    rows, inserts, _ = env
    rows.append({"id": "other", "email": "someone.else@x.example", "organization_id": RIVAL})
    out = _invite()
    assert out["invited"] is True and out["invitation_id"] == "inv_ok"
    assert len(inserts) == 1
    assert inserts[0]["organization_id"] == ORG
    assert inserts[0]["clerk_id"] is None


# ── the audit trail ──────────────────────────────────────────────────────────

def test_success_emits_user_invite(env):
    _, inserts, audits = env
    _invite(role="admin")
    invites = [kw for action, kw in audits if action == "user.invite"]
    assert invites, "account creation left no audit trail at all"
    kw = invites[0]
    assert kw.get("outcome", "success") == "success"
    assert kw["actor_user_id"] == "clerk_admin"
    assert kw["actor_role"] == "super_admin"
    assert kw["organization_id"] == ORG
    assert kw["target_type"] == "user"
    assert kw["target_id"] == inserts[0]["id"]
    assert kw["role"] == "admin" and kw["email"] == TARGET


def test_enumeration_attempts_are_audited_as_denied(env):
    """The caller is told nothing; the operator still sees the probe."""
    rows, _, audits = env
    rows.append({"id": "p1", "email": TARGET, "organization_id": RIVAL})
    with pytest.raises(HTTPException):
        _invite()
    denied = [kw for action, kw in audits
              if action == "user.invite" and kw.get("outcome") == "denied"]
    assert denied, "a cross-tenant probe left no trail"
    assert denied[0]["organization_id"] == ORG
    assert denied[0]["email"] == TARGET


def test_audit_carries_no_secrets(env):
    _, _, audits = env
    _invite()
    for _, kw in audits:
        blob = repr(kw).lower()
        for secret_ish in ("sk_", "token", "password", "bearer"):
            assert secret_ish not in blob, f"audit context carries {secret_ish!r}: {kw}"


# ── the Clerk route to the same oracle ───────────────────────────────────────

class _Resp:
    def __init__(self, payload, status=422):
        self.status_code, self._payload = status, payload
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.mark.parametrize("code,msg", [
    ("form_identifier_exists", "That email address is taken. Please try another."),
    ("duplicate_record", "duplicate email address"),
    ("", "This email address has already been invited."),
])
def test_clerk_duplicate_error_is_not_surfaced_verbatim(monkeypatch, code, msg):
    """Clerk knows every account on the instance, across all tenants — echoing its
    error is the unscoped database check by another route."""
    monkeypatch.setattr(api_server, "_require_clerk_secret_key", lambda: "sk_test_x")
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(
        {"errors": [{"code": code, "message": msg}]}))
    with pytest.raises(HTTPException) as e:
        api_server._create_clerk_invitation(TARGET, "operator", ORG, "https://app/")
    assert e.value.status_code == 409
    assert e.value.detail == api_server._INVITE_REFUSED_DETAIL
    assert TARGET not in str(e.value.detail)


def test_unrelated_clerk_failures_still_surface(monkeypatch):
    """Configuration errors are about us, not the invitee — keep them debuggable."""
    monkeypatch.setattr(api_server, "_require_clerk_secret_key", lambda: "sk_test_x")
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(
        {"errors": [{"code": "authentication_invalid", "message": "Invalid API key"}]}, 401))
    with pytest.raises(HTTPException) as e:
        api_server._create_clerk_invitation(TARGET, "operator", ORG, "https://app/")
    assert e.value.status_code == 502
    assert "Invalid API key" in str(e.value.detail)
