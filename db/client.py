"""Supabase client — singleton, lazy-initialised.

Credentials are resolved from, in order:
  1. Streamlit secrets  [supabase] url/key   (used by the dashboard)
  2. Environment vars   SUPABASE_URL / SUPABASE_KEY  (used by the MCP server)

Returns None gracefully when Supabase is not configured or the package
is not installed, so the dashboard falls back to sample data silently.
"""
from __future__ import annotations

import os

try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_PKG = True
except ImportError:
    _SUPABASE_PKG = False

_client: object | None = None


def _secrets() -> dict | None:
    """Return {url, key} from Streamlit secrets or environment, or None."""
    # 1. Streamlit secrets (dashboard runtime)
    try:
        import streamlit as st
        block = dict(st.secrets["supabase"])
        if block.get("url") and block.get("key"):
            return block
    except Exception:
        pass
    # 2. Environment variables (MCP server / headless runtime)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return {"url": url, "key": key}
    return None


def get_client():
    """Return a live Supabase client or None."""
    global _client
    if _client is not None:
        return _client
    if not _SUPABASE_PKG:
        return None
    cfg = _secrets()
    if not cfg:
        return None
    try:
        _client = create_client(cfg["url"], cfg["key"])
        return _client
    except Exception:
        return None


def is_configured() -> bool:
    """True when secrets are present and the supabase package is installed."""
    return _SUPABASE_PKG and _secrets() is not None
