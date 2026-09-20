"""Shared UUID parsing — replaces shared/objectid.py now that primary keys
are Postgres UUIDs instead of bson ObjectIds.

Every place in this app that converts a caller-supplied id string to a
`uuid.UUID` used to have its own copy of the same
``try: ObjectId(x) except InvalidId: raise ...`` (see the old
objectid.py's docstring) — and, deliberately, different call sites raise
*different* errors on failure:

  - modules/notes/service.py's ``oid()``: 400 "Invalid note id" — an
    authenticated caller editing their own vault gets told plainly the id
    is malformed.
  - modules/public, modules/comments: 404 "Note/Folder/Comment not
    found" — an unauthenticated reader must never be able to distinguish
    "this id is malformed" from "this id doesn't exist" or "this note
    isn't published".

``parse_uuid()`` takes the exception to raise on failure as a parameter
instead of picking one status code for everyone, so every call site keeps
its own existing (different, deliberate) behavior through one shared
implementation instead of N independent copies of the same try/except.
"""

import uuid


def parse_uuid(id_str: str, on_invalid: Exception) -> uuid.UUID:
    try:
        return uuid.UUID(id_str)
    except (ValueError, AttributeError, TypeError):
        raise on_invalid
