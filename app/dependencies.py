"""Deprecated import path — moved to app/shared/dependencies.py as part of
the backend restructure (see PLAN.md). Kept as a thin re-export so every
not-yet-migrated router (see PLAN.md's Phase 3 module list) keeps working
unchanged; delete once nothing imports this."""

from .shared.dependencies import (  # noqa: F401
    get_current_admin,
    get_current_user,
    get_current_user_optional,
    is_admin_email,
)
