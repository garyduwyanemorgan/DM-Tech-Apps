"""core/reasons.py: reason codes are a wire/UI contract and must not drift.

These codes are surfaced to callers (API responses, n8n, the Android app) so a
denial or failure can be told apart programmatically — "no client configured"
vs "RLS denied" vs "plan limit hit" are different remediations. That only works
if the codes are stable strings. This file pins the exact required set so that
renaming or deleting one (even by an innocent refactor) fails CI instead of
silently breaking every caller that switches on the string.

Style follows tests/test_scope_resolution_failure.py: no network, no database.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Imported inside each test via `reasons = pytest.importorskip(...)`-free direct
# import so a missing module fails loudly (collection error) rather than being
# silently skipped — core/reasons.py not existing yet is a red result, not a skip.
import core.reasons as reasons  # noqa: E402


REQUIRED_CODES = {
    "DB_UNAVAILABLE",
    "DB_ERROR",
    "RLS_DENIED",
    "TOKEN_MISSING",
    "ANON_KEY_MISSING",
    "SITE_UNRESOLVED",
    "SCOPE_UNAVAILABLE",
    "PLAN_LIMIT",
    "MISSING_METRIC",
    "PARSE_COLUMN_MISSING",
    "NOT_CONFIGURED",
}


def test_all_required_codes_exist_as_module_attributes():
    missing = sorted(c for c in REQUIRED_CODES if not hasattr(reasons, c))
    assert not missing, f"required reason codes missing from core/reasons.py: {missing}"


def test_all_required_codes_exist_and_are_valid_via_is_valid():
    for code_name in REQUIRED_CODES:
        code_value = getattr(reasons, code_name)
        assert reasons.is_valid(code_value), (
            f"{code_name} = {code_value!r} is not accepted by is_valid(); "
            "a required code must round-trip through validation"
        )


def test_required_codes_have_not_been_renamed_or_removed():
    """A pin against silent drift. If this test goes red, someone renamed or
    deleted a code that other services (API responses, n8n, the Android app)
    switch on by exact string value — that is a breaking wire-contract change,
    not a harmless refactor, and must be deliberate (and versioned), not
    accidental.
    """
    current_values = {getattr(reasons, name) for name in REQUIRED_CODES if hasattr(reasons, name)}
    expected_values = set(REQUIRED_CODES)  # codes are expected to equal their own names
    dropped = expected_values - current_values
    assert not dropped, f"reason codes dropped or renamed: {sorted(dropped)}"


def test_is_valid_rejects_junk():
    for junk in ("", "NOT_A_REAL_CODE", "db_unavailable", "DB-UNAVAILABLE", None, 123):
        assert not reasons.is_valid(junk), f"is_valid() incorrectly accepted {junk!r}"


def test_every_required_code_has_a_nonempty_description():
    for code_name in REQUIRED_CODES:
        code_value = getattr(reasons, code_name)
        description = reasons.describe(code_value) if hasattr(reasons, "describe") else None
        if description is None and hasattr(reasons, "DESCRIPTIONS"):
            description = reasons.DESCRIPTIONS.get(code_value)
        assert description, (
            f"{code_name} has no description — every reason code must be "
            "human-explainable, since it is what a support engineer or the "
            "UI shows for a denial/failure"
        )
        assert isinstance(description, str)
        assert description.strip() == description
        assert len(description) > 5


def test_descriptions_are_unique_per_code():
    """Two codes sharing one description would make the description useless
    for telling failures apart — defeats the purpose of having codes at all.
    """
    descriptions = []
    for code_name in REQUIRED_CODES:
        code_value = getattr(reasons, code_name)
        if hasattr(reasons, "describe"):
            descriptions.append(reasons.describe(code_value))
        elif hasattr(reasons, "DESCRIPTIONS"):
            descriptions.append(reasons.DESCRIPTIONS.get(code_value))
    descriptions = [d for d in descriptions if d]
    assert len(descriptions) == len(set(descriptions)), (
        "some reason codes share an identical description"
    )
