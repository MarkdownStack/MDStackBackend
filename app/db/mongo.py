"""Retired — the app now runs on Postgres.

This file is kept only as a marker (matching this codebase's own history
of leaving a thin, deliberately-broken shim behind a migration — see
backend/SKILL.md's account of app/database.py during the original Mongo
restructure) so a stale `from ..db.mongo import ...` somewhere fails loudly
at import time instead of silently reconnecting to a database nothing else
uses anymore.

See app/db/postgres.py for the engine/session lifecycle and
app/db/models.py for the schema. Safe to delete outright once you've
confirmed nothing still imports this module.
"""

raise ImportError(
    "app.db.mongo was retired by the Postgres migration — see app/db/postgres.py and app/db/models.py instead."
)
