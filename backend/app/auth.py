"""
Single-user password gate.

Flow: POST /auth/login with the password -> receive an opaque token.
Every /api/v1 request must then send  Authorization: Bearer <token>.

The token is an HMAC of the password and SECRET_KEY, so it is stable
(no re-login on every app launch) and is invalidated automatically if
either the password or SECRET_KEY changes. No token is ever stored
server-side, and the password itself is never sent after login.
"""
import hashlib
import hmac

from fastapi import Depends, HTTPException, Request, status

from app.config import get_settings

settings = get_settings()


def auth_enabled() -> bool:
    return bool(settings.APP_PASSWORD)


def make_token() -> str:
    """Deterministic token derived from the password + secret."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        b"macro-tracker-v1:" + settings.APP_PASSWORD.encode(),
        hashlib.sha256,
    ).hexdigest()


def password_ok(candidate: str) -> bool:
    return hmac.compare_digest(candidate or "", settings.APP_PASSWORD)


def token_ok(candidate: str) -> bool:
    return hmac.compare_digest(candidate or "", make_token())


async def require_auth(request: Request) -> None:
    """FastAPI dependency — rejects any request without a valid token."""
    if not auth_enabled():
        return  # no password configured yet; app stays open

    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token:
        token = request.headers.get("x-app-token", "")

    if not token_ok(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorised — please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
