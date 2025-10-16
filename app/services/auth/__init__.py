from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel

from app.models.user import User
from app.utils.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/user/login")


class TokenPair(BaseModel):
    """Pair of JWT tokens used by the client for auth and refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(plain)


def create_token(subject: str, token_version: str, expires_delta: timedelta, token_type: str) -> str:
    """Create a signed JWT with subject, token version, expiration and type."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "tv": token_version,
        "typ": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_tokens(user: User) -> TokenPair:
    """Create access and refresh token pair for a user."""
    access = create_token(
        subject=str(user.id),
        token_version=user.token_version,
        expires_delta=timedelta(minutes=settings.access_token_expires_minutes),
        token_type="access",
    )
    refresh = create_token(
        subject=str(user.id),
        token_version=user.token_version,
        expires_delta=timedelta(days=settings.refresh_token_expires_days),
        token_type="refresh",
    )
    return TokenPair(access_token=access, refresh_token=refresh)


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Auth dependency that validates an access token and returns the user.

    Rejects invalid tokens and tokens with mismatched token versions (logout).
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        token_version: str = payload.get("tv")
        typ: str = payload.get("typ")
        if user_id is None or token_version is None or typ != "access":
            raise HTTPException(status_code=401, detail="Could not validate credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    user = User.objects(id=user_id).first()
    if not user or user.token_version != token_version:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return user


