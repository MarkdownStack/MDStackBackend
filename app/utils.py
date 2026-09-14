"""Deprecated import path — every helper this module used to hold has now
moved (see PLAN.md): extract_links/extract_tags/excerpt to
app/shared/markdown.py, normalize_folder_path/folder_scope_pattern to
app/shared/paths.py, derive_author_name/authors_by_owner_id to
app/modules/users/repository.py, and comment_counts to
app/modules/comments/repository.py (as counts_for_notes) now that that
module exists. Re-exported below so any not-yet-migrated import of
`from ..utils import ...` keeps working unchanged."""

from .modules.comments.repository import counts_for_notes as comment_counts  # noqa: F401
from .modules.users.repository import authors_by_owner_id, derive_author_name  # noqa: F401
from .shared.markdown import excerpt, extract_links, extract_tags  # noqa: F401
from .shared.paths import folder_scope_pattern, normalize_folder_path  # noqa: F401
