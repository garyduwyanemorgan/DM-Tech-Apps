"""Shared secrets access for payment providers.

Thin wrapper over core.config so providers keep a single call site. Each
credential resolves independently through env -> .env -> secrets.toml, so one
value can be overridden by an env var without relocating the whole block.
"""
from __future__ import annotations

from core.config import secret_block


def read_secrets_block(section: str, keys: tuple[str, ...] = ()) -> dict:
    """Return a provider's credentials as a dict (missing values are "")."""
    return secret_block(section, keys)
