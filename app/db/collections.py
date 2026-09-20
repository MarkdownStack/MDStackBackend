"""Retired — the app now runs on Postgres.

Collection handles don't exist anymore; every module's repository.py takes
an `AsyncSession` (see app/db/postgres.py's get_db()) and queries
app/db/models.py's ORM classes instead. Kept as a loud-failure marker —
see app/db/mongo.py's docstring for why. Safe to delete outright once
you've confirmed nothing still imports this module.
"""

raise ImportError(
    "app.db.collections was retired by the Postgres migration — use app/db/models.py's ORM classes "
    "with a session from app/db/postgres.py instead."
)
