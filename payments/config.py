"""Shared secrets access for payment providers.

Providers read their credentials from .streamlit/secrets.toml (a named
section) with environment variables as fallback — the same pattern the
original Stripe integration used.
"""
from __future__ import annotations

import pathlib
import tomllib

# Project root = parent of the payments/ package
_SECRETS_PATH = pathlib.Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def read_secrets_block(section: str) -> dict:
    """Return one [section] of secrets.toml as a dict ({} if missing/unreadable)."""
    try:
        with open(_SECRETS_PATH, "rb") as f:
            data = tomllib.load(f)
        return dict(data.get(section, {}) or {})
    except Exception:
        return {}
