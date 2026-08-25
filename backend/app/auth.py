"""
Single-user password gate.

The password is stored in the database as a PBKDF2-HMAC-SHA256 hash
(random 16-byte salt, 600k iterations — OWASP's 2023 guidance) and is
set/changed from My Account inside the app. Plaintext is never stored.

Login returns an opaque token = HMAC(SECRET_KEY, password_hash), so:
  • the password is never sent again after login
  • changing the password invalidates every existing token (signs out all devices)

APP_PASSWORD (env) still works as a bootstrap/fallback for a deployment that
has no password in the database yet.
"""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import User

settings = get_settings()

DEFAULT_USER_EMAIL = "jesse@macro.app"
_ITERATIONS = 600_000
MIN_PASSWORD_LEN = 8


# ── Hashing ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """-> 'pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>'"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode(),
            base64.b64decode(salt_b64), int(iters),
        )
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


# ── Current credential (DB first, env as fallback) ───────────────────────────

async def _get_user(db: AsyncSession) -> User | None:
    res = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    return res.scalar_one_or_none()


async def current_secret(db: AsyncSession) -> str | None:
    """
    The value tokens are derived from:
      • the stored password hash, if a password has been set in the app
      • else the APP_PASSWORD env var (bootstrap)
      • else None -> auth disabled
    """
    user = await _get_user(db)
    if user and user.password_hash:
        return user.password_hash
    if settings.APP_PASSWORD:
        return "env:" + settings.APP_PASSWORD
    return None


def token_for(secret: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        b"macro-tracker-v2:" + secret.encode(),
        hashlib.sha256,
    ).hexdigest()


async def check_password(db: AsyncSession, candidate: str) -> bool:
    """Verify a plaintext password against the DB hash, or the env fallback."""
    user = await _get_user(db)
    if user and user.password_hash:
        return verify_password(candidate, user.password_hash)
    if settings.APP_PASSWORD:
        return hmac.compare_digest(candidate or "", settings.APP_PASSWORD)
    return False


async def set_password(db: AsyncSession, new_password: str) -> None:
    user = await _get_user(db)
    if not user:
        user = User(email=DEFAULT_USER_EMAIL, name="Jesse")
        db.add(user)
        await db.flush()
    user.password_hash = hash_password(new_password)
    user.password_updated_at = datetime.now(timezone.utc)
    await db.flush()


# ── Request gate ─────────────────────────────────────────────────────────────

def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-app-token", "")


async def require_auth(request: Request, db: AsyncSession = Depends(get_db)) -> None:
    secret = await current_secret(db)
    if secret is None:
        return  # no password configured anywhere — app stays open
    if not hmac.compare_digest(_bearer(request), token_for(secret)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorised — please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
