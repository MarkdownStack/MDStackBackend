"""Request/response models for accounts, auth, and email verification/reset
— moved from app/models.py."""

from pydantic import BaseModel, EmailStr, Field

# Letters, numbers, and underscores only — no dots/spaces (keeps it
# unambiguous as a login identifier alongside an email address, and safe to
# show as a byline with no further sanitizing).
USERNAME_PATTERN = r"^[a-zA-Z0-9_]{3,24}$"


class UserCreate(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    username: str = ""
    email: str
    is_verified: bool = False
    is_subscribed: bool = False
    # Computed from Settings.admin_email_set (see shared/dependencies.py),
    # not stored — lets the frontend show/hide admin-only UI (the admin
    # dashboard entry in SettingsMenu) without guessing, while the actual
    # gate on every admin endpoint still re-checks server-side via
    # get_current_admin.
    is_admin: bool = False
    created_at: str
    updated_at: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Email verification ------------------------------------------------
# Registering creates the account immediately but leaves is_verified=False
# on the user document until the link Mailgun sends (see email.py) is
# clicked — /api/auth/login refuses unverified accounts (403, not 401,
# since the credentials themselves were correct) so a signup that never
# checks their inbox can't silently end up "logged in but unconfirmed".


class ResendVerificationRequest(BaseModel):
    # Email or username — login now accepts either (see service.py's
    # login), so "resend my verification email" has to accept whichever one
    # someone actually remembers signing in with.
    identifier: str


class MessageOut(BaseModel):
    message: str


# ---- Forgot / reset password -------------------------------------------
# Same shape as email verification (a random token + expiry stored on the
# user document, emailed as a link) — see service.py's
# forgot_password/reset_password and email.py's send_password_reset_email.
# Kept as its own token field (password_reset_token) rather than reusing
# verification_token so a pending signup-verification link and a pending
# password-reset link can never collide or invalidate each other on the
# same account.


class ForgotPasswordRequest(BaseModel):
    # Same reasoning as ResendVerificationRequest.identifier above.
    identifier: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)
