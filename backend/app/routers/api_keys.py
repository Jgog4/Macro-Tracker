"""
/api-keys — manage external access tokens (Mac dashboard, spreadsheet, etc.)

Keys are hashed with SHA-256 before storage.
The plaintext key is shown exactly once on creation.
Authenticate external requests with: Authorization: Bearer <raw_key>
"""
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import ApiKey, User
from app.routers.meals import _get_or_create_user
from app.schemas.schemas import ApiKeyCreate, ApiKeyRead

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/", response_model=ApiKeyRead, status_code=status.HTTP_201_CREATED)
async def create_api_key(body: ApiKeyCreate, db: AsyncSession = Depends(get_db)):
    """
    Generate a new API key.
    ⚠️  The raw key is returned ONCE — store it securely.
    Subsequent requests authenticate with: Authorization: Bearer <raw_key>
    """
    user = await _get_or_create_user(db)
    raw_key  = "mt_" + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)

    api_key = ApiKey(user_id=user.id, name=body.name, key_hash=key_hash)
    db.add(api_key)
    await db.flush()

    response = ApiKeyRead.model_validate(api_key)
    response.raw_key = raw_key   # only time raw key is exposed
    return response


@router.get("/", response_model=list[ApiKeyRead])
async def list_api_keys(db: AsyncSession = Depends(get_db)):
    user = await _get_or_create_user(db)
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at)
    )
    return result.scalars().all()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: str, db: AsyncSession = Depends(get_db)):
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.delete(key)
