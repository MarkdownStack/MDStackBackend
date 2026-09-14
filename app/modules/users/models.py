"""Mongo document -> response schema mapping for users — moved from
routers/auth.py's _user_out()."""

from ...shared.dependencies import is_admin_email
from .schemas import UserOut


def to_user_out(doc: dict) -> UserOut:
    return UserOut(
        id=str(doc["_id"]),
        username=doc.get("username", ""),
        email=doc["email"],
        is_verified=doc.get("is_verified", False),
        is_admin=is_admin_email(doc.get("email")),
        created_at=doc.get("created_at", ""),
        updated_at=doc.get("updated_at", doc.get("created_at", "")),
    )
