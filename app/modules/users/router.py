"""HTTP binding for /api/auth. All business logic lives in service.py;
this file only translates requests to service calls and back, so route
paths, status codes, and response_models are exactly what they were
before this migration."""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...shared.dependencies import get_current_user
from . import service
from .schemas import (
    ForgotPasswordRequest,
    MessageOut,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    return await service.register(db, payload)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    return await service.login(db, form_data.username, form_data.password)


@router.get("/verify-email", response_model=MessageOut)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    message = await service.verify_email(db, token)
    return MessageOut(message=message)


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(payload: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    message = await service.resend_verification(db, payload.identifier)
    return MessageOut(message=message)


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await service.forgot_password(db, payload.identifier)
    return MessageOut(message=message)


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    message = await service.reset_password(db, payload.token, payload.password)
    return MessageOut(message=message)


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.get_profile(db, current_user["_id"])
