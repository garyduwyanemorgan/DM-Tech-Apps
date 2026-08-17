"""Stable, machine-readable reason codes for silent failure paths.

This codebase's characteristic failure mode is SILENCE, not exceptions: roughly
forty `except Exception: return []` / `return False` / `return 0` handlers in
db/queries.py mean "no data", "you were denied by RLS", "the database is
unreachable" and "the token was dropped" are all indistinguishable to callers
and to the UI — which then renders sample data and looks healthy.

`core.scope.ScopeUnavailable` proved the fix once: an unknown scope is not an
empty one. This module generalises that idea into a flat set of codes so every
swallowed failure can *testify* (via core.audit.emit) instead of vanishing.
The UX fallback (`[]`, `None`, `False`, `0`) is unchanged — these codes ride
alongside it in the audit event, not in the return value.

Free text is banned here on purpose: a reason code must be aggregatable
("how many RLS_DENIED events this week") and must drive UI (a banner, a
tooltip), which a sentence in a log line cannot do reliably. Codes are plain
module-level string constants rather than an Enum so a bare string ("DB_ERROR")
compares equal and serialises to JSON without a `.value` — every call site is
either core.audit.emit(...) (JSON) or a UI label lookup, never arithmetic.
"""
from __future__ import annotations

# ── Codes ─────────────────────────────────────────────────────────────────────

DB_UNAVAILABLE = "DB_UNAVAILABLE"          # client could not be constructed (create/auth failed)
DB_ERROR = "DB_ERROR"                      # a query raised; the DB was reachable but the call failed
RLS_DENIED = "RLS_DENIED"                  # suspected Row-Level Security denial (see note below)
TOKEN_MISSING = "TOKEN_MISSING"            # a token-scoped read was attempted with no token
ANON_KEY_MISSING = "ANON_KEY_MISSING"      # SUPABASE_ANON_KEY not configured; scoped client refused
SITE_UNRESOLVED = "SITE_UNRESOLVED"        # a site name could not be resolved to an id
SCOPE_UNAVAILABLE = "SCOPE_UNAVAILABLE"    # core.scope / ScopeUnavailable: assignment data unreadable
PLAN_LIMIT = "PLAN_LIMIT"                  # request refused by a billing/plan limit
MISSING_METRIC = "MISSING_METRIC"          # an expected parameter/column had no value
PARSE_COLUMN_MISSING = "PARSE_COLUMN_MISSING"  # extraction/parsing expected a column that wasn't present
NOT_CONFIGURED = "NOT_CONFIGURED"          # feature/package/integration not installed or configured
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"      # an unclassified exception; see context.exception_type

# Note on RLS_DENIED: PostgREST does NOT raise on a Row-Level Security denial —
# a denied row and an absent row both read back as zero rows. A token-scoped
# read that comes back empty is therefore only a *suspected* RLS denial, never
# a confirmed one; a genuinely empty tenant looks identical. Callers emitting
# this code must carry that ambiguity forward (e.g. `suspected=True` in the
# audit event context) rather than asserting denial as fact.

DESCRIPTIONS: dict[str, str] = {
    DB_UNAVAILABLE: "The database client could not be constructed (create/auth failure).",
    DB_ERROR: "A database query raised an exception; the database was reachable but the call failed.",
    RLS_DENIED: "Suspected Row-Level Security denial — a token-scoped read returned zero rows. "
                "This is ambiguous: an empty tenant looks identical to a denied one.",
    TOKEN_MISSING: "A token-scoped read was attempted with no caller token available.",
    ANON_KEY_MISSING: "SUPABASE_ANON_KEY is not configured, so a token-scoped client was refused "
                       "rather than falling back to service_role.",
    SITE_UNRESOLVED: "A site name could not be resolved to a site id within the caller's organization.",
    SCOPE_UNAVAILABLE: "User site/project assignment data could not be read, so scope is unknown "
                        "— not empty.",
    PLAN_LIMIT: "The request was refused by a billing/plan limit (e.g. site count).",
    MISSING_METRIC: "An expected parameter or metric had no recorded value.",
    PARSE_COLUMN_MISSING: "Extraction/parsing expected a column that was not present in the source.",
    NOT_CONFIGURED: "The feature, package, or integration required for this call is not configured.",
    UNEXPECTED_ERROR: "An exception with no specific reason code. The exception class name is "
                      "recorded in the event context as `exception_type`, never here — this "
                      "vocabulary must stay closed and countable.",
}

# All valid codes, for is_valid() and for anyone enumerating the registry.
ALL_CODES: frozenset[str] = frozenset(DESCRIPTIONS)


def is_valid(code: str) -> bool:
    """True iff `code` is a known reason code."""
    return code in DESCRIPTIONS


def describe(code: str) -> str:
    """Human-readable description for a code, or a fallback for an unknown one."""
    return DESCRIPTIONS.get(code, f"Unknown reason code: {code!r}")
