"""/auth — sign in to the app. These endpoints are deliberately unprotected."""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import auth_enabled, make_token, password_ok, token_ok

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str


class StatusResponse(BaseModel):
    auth_required: bool
    authenticated: bool


@router.get("/status", response_model=StatusResponse)
async def auth_status(token: str = ""):
    """Does this deployment require a password, and is the supplied token valid?"""
    return StatusResponse(
        auth_required=auth_enabled(),
        authenticated=(not auth_enabled()) or token_ok(token),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    if not auth_enabled():
        return LoginResponse(token="")          # no password configured
    if not password_ok(body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )
    return LoginResponse(token=make_token())
