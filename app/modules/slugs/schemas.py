"""Request/response models for the slug-redirect feature.

Slugs are globally unique, URL-safe identifiers chosen by a note/folder
owner to give their published content a memorable short URL instead of a
raw UUID. E.g. BASE_URL/p/s/python-oop-concepts instead of
BASE_URL/p/3f2a1b...
"""

import re

from pydantic import BaseModel, field_validator

# Slug rules, validated here and documented in SlugRedirect's ORM docstring:
# - 3–80 characters
# - lowercase letters, digits, and hyphens only
# - cannot start or end with a hyphen (looks like a typo, breaks some URL
#   parsers)
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]$|^[a-z0-9]{3,80}$")


class SlugSet(BaseModel):
    """Body for PUT /api/slugs/note/{note_id} and
    PUT /api/slugs/folder/{folder_id}."""

    slug: str

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Slug must be 3–80 characters, use only lowercase letters, "
                "digits, and hyphens, and cannot start or end with a hyphen."
            )
        return v


class SlugOut(BaseModel):
    """Returned after a successful slug set or on GET for the current slug."""

    slug: str
    target_type: str  # "note" | "folder"
    target_id: str
    short_url: str   # fully qualified public URL the caller can copy


class SlugAvailability(BaseModel):
    """Returned by GET /api/slugs/check/{slug}."""

    slug: str
    available: bool


class SlugResolve(BaseModel):
    """Returned by the public GET /api/public/s/{slug} resolution endpoint.
    The frontend uses this to decide which route to navigate to — it never
    redirects at the HTTP level (a 302 would require the frontend to follow
    it cross-origin and re-attach the auth header) so it returns JSON
    instead and lets the React router do the navigation.
    """

    target_type: str  # "note" | "folder"
    target_id: str
