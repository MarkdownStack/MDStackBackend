"""Timestamp helpers.

`now_iso()` is unchanged from before this migration — still handy for
domain values that are genuinely just "a moment in time as a string" (a
verification-token expiry embedded in an email link, say), independent of
any particular database row.

`iso()` is new: every note/folder/user/comment "created_at"/"updated_at"
in the API response schemas is (and remains, for frontend compatibility) a
plain ISO-8601 string, but the Postgres columns backing them are now real
`datetime` values (see db/models.py — Postgres, unlike a Mongo document,
actually enforces a column's type, so "sometimes a string, sometimes
whatever the app happened to serialize" wasn't an option here). Every
module's `models.py` mapper calls this once per timestamp field instead of
each writing its own `dt.isoformat() if dt else default` inline.
"""

from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso(value: datetime | None, default: str = "") -> str:
    """`value.isoformat()`, or `default` if there's no value at all (a
    folder created via upload's ensure_folder_chain has no created_at/
    updated_at at all — see db/models.py's Folder docstring)."""
    return value.isoformat() if value is not None else default
