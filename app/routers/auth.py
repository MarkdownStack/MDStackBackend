from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..auth import create_access_token, hash_password, verify_password
from ..database import users_collection
from ..dependencies import get_current_user
from ..models import Token, UserCreate, UserOut, now_iso

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserCreate):
    email = payload.email.lower()
    existing = await users_collection.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    ts = now_iso()
    doc = {
        "email": email,
        "password_hash": hash_password(payload.password),
        "created_at": ts,
        "updated_at": ts,
    }
    result = await users_collection.insert_one(doc)
    return UserOut(id=str(result.inserted_id), email=email, created_at=ts, updated_at=ts)


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

    access_token = create_access_token(data={"sub": str(user["_id"])})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserOut)
async def read_current_user(current_user: dict = Depends(get_current_user)):
    # The one endpoint that actually needs more than the user's id —
    # get_current_user no longer fetches the full document itself (see its
    # docstring), so this fetches it explicitly, just for this rarer call.
    user = await users_collection.find_one({"_id": current_user["_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user.get("created_at", ""),
        updated_at=user.get("updated_at", user.get("created_at", "")),
    )
