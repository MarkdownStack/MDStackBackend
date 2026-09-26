"""ORM object -> response schema mapping for users."""

from ...db.models import User
from ...shared.datetime import iso
from ...shared.dependencies import is_admin_email
from .schemas import UserOut


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        username=user.username or "",
        email=user.email,
        is_verified=user.is_verified,
        is_subscribed=user.is_subscribed,
        is_admin=is_admin_email(user.email),
        created_at=iso(user.created_at),
        updated_at=iso(user.updated_at, iso(user.created_at)),
    )
