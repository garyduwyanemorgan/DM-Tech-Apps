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
    """Return {url, key} from Streamlit secrets, secrets.toml file, or env vars."""
    # 1. Streamlit secrets (dashboard runtime)
    try:
        import streamlit as st
        block = dict(st.secrets["supabase"])
        if block.get("url") and block.get("key"):
            return block
    except Exception:
        pass
    # 2. Read .streamlit/secrets.toml directly (FastAPI / uvicorn runtime)
    try:
        import tomllib
        import pathlib
        toml_path = pathlib.Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        block = data.get("supabase", {})
        if block.get("url") and block.get("key"):
            return block
    except Exception:
        pass
    # 3. Environment variables (CI / cloud runtime)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return {"url": url, "key": key}
    return None


def get_client(token: str | None = None):
    """Return a live Supabase client, optionally scoped with a user's JWT token."""
    global _client
    if not _SUPABASE_PKG:
        return None
    cfg = _secrets()
    if not cfg:
        return None
    try:
        if token:
            # Create a request-scoped client for this specific request context
            # to enforce Row-Level Security safely without concurrent race conditions.
            scoped_client = create_client(cfg["url"], cfg["key"])
            scoped_client.postgrest.auth(token)
            return scoped_client

        global _client
        if _client is not None:
            return _client
        _client = create_client(cfg["url"], cfg["key"])
        return _client
    except Exception:
        return None


def is_configured() -> bool:
    """True when secrets are present and the supabase package is installed."""
    return _SUPABASE_PKG and _secrets() is not None
