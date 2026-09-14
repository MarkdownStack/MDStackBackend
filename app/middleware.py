"""Deprecated import path — moved to app/core/middleware.py as part of the
backend restructure (see PLAN.md). Kept as a thin re-export in case
anything still imports from here; delete once nothing does."""

from .core.middleware import RequestCounterMiddleware  # noqa: F401
