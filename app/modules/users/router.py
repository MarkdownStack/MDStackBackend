"""HTTP binding for /api/auth — moved from app/routers/auth.py. All
business logic lives in service.py now; this file only translates
requests to service calls and back, so route paths, status codes, and
response_models are exactly what they were before."""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

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
async def register(payload: UserCreate):
    return await service.register(payload)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    return await service.login(form_data.username, form_data.password)


@router.get("/verify-email", response_model=MessageOut)
async def verify_email(token: str):
    message = await service.verify_email(token)
    return MessageOut(message=message)


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(payload: ResendVerificationRequest):
    message = await service.resend_verification(payload.identifier)
    return MessageOut(message=message)


@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(payload: ForgotPasswordRequest):
    message = await service.forgot_password(payload.identifier)
    return MessageOut(message=message)


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(payload: ResetPasswordRequest):
    message = await service.reset_password(payload.token, payload.password)
    return MessageOut(message=message)


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: dict = Depends(get_current_user)):
    return await service.get_profile(current_user["_id"])
