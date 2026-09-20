"""Retired — the app now runs on Postgres.

Indexes are declared as part of each table in app/db/models.py
(`__table_args__`) and created by app/db/postgres.py's init_db() (or, for
a real multi-environment rollout, the Alembic revisions under
backend/alembic/ — see POSTGRES_MIGRATION.md). There's no separate
ensure_indexes() step anymore. Kept as a loud-failure marker — see
app/db/mongo.py's docstring for why. Safe to delete outright once you've
confirmed nothing still imports this module.
"""

raise ImportError(
    "app.db.indexes was retired by the Postgres migration — see app/db/postgres.py's init_db() "
    "and app/db/models.py's __table_args__ instead."
)
