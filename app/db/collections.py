"""Collection handles — moved from the bottom half of app/database.py.

Kept as plain module-level globals (created eagerly, same as today) rather
than accessor functions: every router currently imports these directly
(e.g. ``from ..database import notes_collection``), and changing that shape
is exactly the kind of collateral change Phase 3 handles one module at a
time — not bundled into this plumbing-only phase. app/database.py re-
exports these unchanged so every existing import keeps working.
"""

from .mongo import db

users_collection = db["users"]
notes_collection = db["notes"]
folders_collection = db["folders"]
comments_collection = db["comments"]
# One doc per UTC calendar day (`_id` is the "YYYY-MM-DD" string itself, so
# there's no separate index to maintain — see core/middleware.py, which is
# the only writer, and modules/admin, which reads it back for the admin
# dashboard's request-count stats).
request_stats_collection = db["request_stats"]
