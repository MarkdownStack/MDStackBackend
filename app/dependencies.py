import jwt
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .auth import decode_access_token
from .database import users_collection

# tokenUrl points the interactive docs (/docs) at the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode the bearer token and load the corresponding user document.

    Raises 401 for any missing/invalid/expired token or unknown user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    try:
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        raise credentials_exception

    if user is None:
        raise credentials_exception

    return user
