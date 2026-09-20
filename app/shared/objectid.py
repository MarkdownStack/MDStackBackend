"""Retired — primary keys are Postgres UUIDs now, not bson ObjectIds.

See app/shared/ids.py's parse_uuid() instead. Kept as a loud-failure
marker (see app/db/mongo.py's docstring for why this pattern is used
throughout this migration) rather than deleted outright. Safe to delete
once you've confirmed nothing still imports this module.
"""

raise ImportError("app.shared.objectid was retired by the Postgres migration — use app.shared.ids.parse_uuid instead.")
