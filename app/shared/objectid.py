"""Shared ObjectId parsing.

Every place in this app that converts a caller-supplied id string to a bson
ObjectId used to have its own copy of the same
``try: ObjectId(x) except InvalidId: raise ...`` — and, deliberately,
different call sites raise *different* errors on failure:

  - app/routers/notes.py's ``oid()``: 400 "Invalid note id" — an
    authenticated caller editing their own vault gets told plainly the id
    is malformed.
  - app/routers/public.py: 404 "Note/Folder/Comment not found" — an
    unauthenticated reader must never be able to distinguish "this id is
    malformed" from "this id doesn't exist" or "this note isn't
    published" (see get_public_note_doc's docstring).

``parse_object_id()`` takes the exception to raise on failure as a
parameter instead of picking one status code for everyone, so every call
site keeps its own existing (different, deliberate) behavior through one
shared implementation instead of N independent copies of the same
try/except.
"""

from bson import ObjectId
from bson.errors import InvalidId


def parse_object_id(id_str: str, on_invalid: Exception) -> ObjectId:
    try:
        return ObjectId(id_str)
    except InvalidId:
        raise on_invalid
