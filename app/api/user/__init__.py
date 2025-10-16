from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError

from app.models.user import User
from app.utils.config import settings
from app.services.auth import (
    TokenPair,
    verify_password,
    get_current_user,
    create_tokens,
    hash_password,
)


router = APIRouter()


class SignupBody(BaseModel):
    name: str
    email: EmailStr
    password: str

@router.post("/signup", response_model=TokenPair)
def signup(body: SignupBody) -> TokenPair:
    # Reject duplicate email signups early
    if User.objects(email=body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    # Hash password before storing; return tokens so client is logged in
    user = User(name=body.name, email=body.email, password=hash_password(body.password))
    user.save()
    return create_tokens(user)


@router.post("/login", response_model=TokenPair)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenPair:
    # Find user by email (username field of OAuth2PasswordRequestForm)
    user = User.objects(email=form_data.username).first()
    # Validate password; avoid leaking whether email exists
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_tokens(user)


class RefreshBody(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenPair)
def refresh_token(body: RefreshBody) -> TokenPair:
    # Decode refresh token and validate token type
    try:
        payload = jwt.decode(body.refresh_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("typ") != "refresh":
            raise JWTError()
        user_id: str = payload.get("sub")
        token_version: str = payload.get("tv")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # Ensure the user exists and token version matches (not logged out)
    user = User.objects(id=user_id).first()
    if not user or user.token_version != token_version:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return create_tokens(user)


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user)) -> dict:
    # Bump token_version so existing tokens become invalid immediately
    current_user.token_version = str(int(current_user.token_version) + 1)
    current_user.save()
    return {"status": True}


