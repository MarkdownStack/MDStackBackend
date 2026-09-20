"""Pure folder-path helpers.

`folder_scope_pattern()`'s regex is gone as part of the Postgres migration
(the brief calls for no regular expressions anywhere in the new code) —
in its place, `folder_scope_clause()` builds the equivalent SQL `WHERE`
condition directly (`path = :p OR path LIKE :p || '/%'`, with `%`/`_`/`\`
escaped as literals via ordinary string replacement, not a regex), and
`path_in_scope()` is the same "this path or anything nested under it"
test done in plain Python for the few call sites that check it against an
already-fetched value instead of building a query.
"""

from sqlalchemy import ColumnElement, or_


def normalize_folder_path(path: str) -> str:
    path = (path or "").strip().strip("/")
    # collapse duplicate slashes
    parts = [p for p in path.split("/") if p]
    return "/".join(parts)


# The three characters LIKE treats specially: '%' (any run of characters),
# '_' (any single character), and the escape character itself. A folder
# path is free-form user text and could contain any of them literally, so
# every one gets escaped with a backslash before being used as a LIKE
# pattern — plain str.replace() calls, not a regex, and in this exact
# order so an already-escaped '%'/'_' from an earlier replace() call never
# gets re-escaped by a later one.
def _escape_for_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def folder_scope_clause(column: ColumnElement, path: str) -> ColumnElement:
    """'This folder or anything nested under it', as a SQLAlchemy WHERE
    condition on `column` (a `folder_path` or `path` column) — matches
    `path` itself and `path/...` but never an unrelated sibling that
    merely starts with the same characters (e.g. selecting "notes" must
    not also match "notes-archive"). Used by every place that needs to
    scope a query to a folder's whole subtree: the recursive folder-
    delete, the published-folder note-count/listing endpoints, and
    export's folder selection (modules/folders, modules/public,
    modules/export) — the direct Postgres equivalent of the old
    folder_scope_pattern() regex, built from LIKE instead."""
    escaped = _escape_for_like(path)
    return or_(column == path, column.like(f"{escaped}/%", escape="\\"))


def path_in_scope(candidate_path: str, scope_path: str) -> bool:
    """Plain-Python version of folder_scope_clause(), for the one call
    site (modules/public/service.py's get_public_folder_note) that
    re-checks an already-fetched note's folder_path against a folder's
    published path rather than building a query — was `re.match(...)`,
    now just string equality/startswith."""
    return candidate_path == scope_path or candidate_path.startswith(scope_path + "/")
