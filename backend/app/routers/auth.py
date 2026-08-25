"""/auth — sign in and manage the account password. Deliberately unprotected."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    MIN_PASSWORD_LEN, _bearer, check_password, current_secret,
    set_password, token_for,
)
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str


class StatusResponse(BaseModel):
    auth_required:  bool   # is a password configured at all?
    authenticated:  bool   # is the caller's token valid?
    password_is_set: bool  # set from inside the app (vs env fallback)


class SetPasswordRequest(BaseModel):
    current_password: str | None = None
    new_password:     str


@router.get("/status", response_model=StatusResponse)
async def auth_status(request: Request, db: AsyncSession = Depends(get_db)):
    secret = await current_secret(db)
    ok = secret is None or _bearer(request) == token_for(secret)
    return StatusResponse(
        auth_required=secret is not None,
        authenticated=ok,
        password_is_set=bool(secret and not secret.startswith("env:")),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    secret = await current_secret(db)
    if secret is None:
        return TokenResponse(token="")           # nothing configured yet
    if not await check_password(db, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect password.")
    return TokenResponse(token=token_for(secret))


@router.post("/password", response_model=TokenResponse)
async def change_password(body: SetPasswordRequest, request: Request,
                          db: AsyncSession = Depends(get_db)):
    """
    Set or change the app password.

    If one already exists you must prove you know it — either by sending
    current_password, or by holding a valid token (i.e. already signed in).
    """
    if len(body.new_password or "") < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LEN} characters.",
        )

    secret = await current_secret(db)
    if secret is not None:
        signed_in = _bearer(request) == token_for(secret)
        knows_old = body.current_password is not None and \
            await check_password(db, body.current_password)
        if not (signed_in or knows_old):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Current password is incorrect.")

    await set_password(db, body.new_password)

    # New hash => new token. Every other device is signed out.
    new_secret = await current_secret(db)
    return TokenResponse(token=token_for(new_secret))
