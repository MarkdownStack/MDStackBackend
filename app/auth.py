"""Deprecated import path — moved to app/core/security.py as part of the
backend restructure (see PLAN.md). Kept as a thin re-export so any
not-yet-migrated import keeps working; delete once nothing imports this."""

from .core.security import (  # noqa: F401
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
