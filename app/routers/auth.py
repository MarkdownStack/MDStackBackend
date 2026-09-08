import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..auth import create_access_token, hash_password, verify_password
from ..database import users_collection
from ..dependencies import get_current_user
from ..email import send_password_reset_email, send_verification_email
from ..models import (
    ForgotPasswordRequest,
    MessageOut,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserOut,
    now_iso,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# How long a verification link stays clickable before /verify-email starts
# rejecting it (and the user has to hit "resend" to get a fresh one).
VERIFICATION_TOKEN_TTL = timedelta(hours=24)

# Deliberately much shorter than the verification token above — a password
# reset link grants "set this account's password" outright (no old password
# needed), so a short window matters more here than for email verification.
PASSWORD_RESET_TOKEN_TTL = timedelta(hours=1)


def _new_token(ttl: timedelta) -> tuple[str, str]:
    """Returns (token, ISO-8601 expiry) for a fresh single-use link."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + ttl).isoformat()
    return token, expires_at


def _new_verification_token() -> tuple[str, str]:
    return _new_token(VERIFICATION_TOKEN_TTL)


def _user_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        is_verified=user.get("is_verified", False),
        created_at=user.get("created_at", ""),
        updated_at=user.get("updated_at", user.get("created_at", "")),
    )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserCreate):
    email = payload.email.lower()
    existing = await users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    ts = now_iso()
    token, expires_at = _new_verification_token()
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "is_verified": False,
        "verification_token": token,
        "verification_token_expires": expires_at,
        "created_at": ts,
        "updated_at": ts,
    }
    result = await users_collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Best-effort: registration still succeeds even if Mailgun is down or
    # unconfigured (see send_verification_email's docstring) — the account
    # exists either way, "resend verification" is the recovery path.
    await send_verification_email(email, token)

    return _user_out(doc)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # OAuth2PasswordRequestForm uses "username" as the field name; we treat it as the email.
    email = form_data.username.lower()
    user = await users_collection.find_one({"email": email})
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_verified", False):
        # 403, not 401 — the credentials themselves were correct, the
        # account just isn't activated yet. AuthPage.jsx keys off this
        # status specifically to show "resend verification" instead of a
        # generic wrong-password error.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )

    access_token = create_access_token(data={"sub": str(user["_id"])})
    return Token(access_token=access_token)


@router.get("/verify-email", response_model=MessageOut)
async def verify_email(token: str):
    user = await users_collection.find_one({"verification_token": token})
    if not user:
        raise HTTPException(status_code=400, detail="This verification link is invalid or has already been used.")

    if user.get("is_verified"):
        return MessageOut(message="Your email is already verified — you can log in.")

    expires_raw = user.get("verification_token_expires")
    if expires_raw and datetime.now(timezone.utc) > datetime.fromisoformat(expires_raw):
        raise HTTPException(
            status_code=400,
            detail="This verification link has expired. Request a new one from the login page.",
        )

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"is_verified": True, "updated_at": now_iso()},
            "$unset": {"verification_token": "", "verification_token_expires": ""},
        },
    )
    return MessageOut(message="Email verified! You can now log in.")


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(payload: ResendVerificationRequest):
    email = payload.email.lower()
    user = await users_collection.find_one({"email": email})

    # Identical response whether the account exists, is already verified,
    # or genuinely gets a new email — so this endpoint can't be used to
    # probe which addresses have an account.
    generic = MessageOut(message="If that account exists and needs verifying, a new link is on its way.")

    if not user or user.get("is_verified"):
        return generic

    token, expires_at = _new_verification_token()
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"verification_token": token, "verification_token_expires": expires_at, "updated_at": now_iso()}},
    )
    await send_verification_email(email, token)
    return generic


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(payload: ForgotPasswordRequest):
    email = payload.email.lower()
    user = await users_collection.find_one({"email": email})

    # Same generic response regardless of whether the account exists — see
    # resend_verification above for why (email-enumeration prevention).
    generic = MessageOut(message="If that account exists, a password reset link is on its way.")

    if not user:
        return generic

    token, expires_at = _new_token(PASSWORD_RESET_TOKEN_TTL)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_reset_token": token, "password_reset_token_expires": expires_at, "updated_at": now_iso()}},
    )
    await send_password_reset_email(email, token)
    return generic


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(payload: ResetPasswordRequest):
    user = await users_collection.find_one({"password_reset_token": payload.token})
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has already been used.")

    expires_raw = user.get("password_reset_token_expires")
    if expires_raw and datetime.now(timezone.utc) > datetime.fromisoformat(expires_raw):
        raise HTTPException(
            status_code=400,
            detail="This reset link has expired. Request a new one from the login page.",
        )

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password_hash": hash_password(payload.password), "updated_at": now_iso()},
            # Both single-use — a spent (or now-superseded) reset token
            # must never work again, same as verification_token on success.
            "$unset": {"password_reset_token": "", "password_reset_token_expires": ""},
        },
    )
    return MessageOut(message="Password reset! You can now log in with your new password.")


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: dict = Depends(get_current_user)):
    # The one endpoint that actually needs more than the user's id —
    # get_current_user no longer fetches the full document itself (see its
    # docstring), so this fetches it explicitly, just for this rarer call.
    user = await users_collection.find_one({"_id": current_user["_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_out(user)
