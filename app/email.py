"""Deprecated import path — moved to app/modules/users/email.py as part of
the backend restructure (see PLAN.md). Kept as a thin re-export in case
anything still imports from here; delete once nothing does."""

from .modules.users.email import send_password_reset_email, send_verification_email  # noqa: F401
