"""now_iso() — moved out of app/models.py.

Not a schema, so it doesn't belong there — every router calls this to
stamp created_at/updated_at, independent of any particular module's
request/response models.
"""

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
