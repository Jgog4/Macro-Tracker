"""
/vision — upload a photo of a nutrition label or restaurant menu.
GPT-4o-mini extracts macros and returns them as JSON for review before saving.
"""
import base64
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient
from app.schemas.schemas import VisionExtractResponse, IngredientRead
from app.services.vision_ocr import extract_nutrition_from_image

router = APIRouter(prefix="/vision", tags=["Vision / OCR"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@router.post("/extract", response_model=VisionExtractResponse)
async def extract_from_image(
    file: UploadFile = File(..., description="Photo of nutrition label or menu"),
):
    """
    Upload a nutrition label / menu photo.
    Returns structured macro data extracted by GPT-4o-mini.
    Does NOT save to DB — review the result first, then POST to /foods/ or /meals/.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{file.content_type}'. Use JPEG, PNG, or WebP.",
        )

    image_bytes = await file.read()
    if len(image_bytes) > 20 * 1024 * 1024:  # 20 MB limit
        raise HTTPException(status_code=413, detail="Image too large (max 20 MB)")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    result = await extract_nutrition_from_image(b64, file.content_type or "image/jpeg")
    return result


@router.post("/extract-and-save", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def extract_and_save(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None, description="Override the extracted name"),
    db:   AsyncSession = Depends(get_db),
):
    """
    Extract macros from image AND immediately save as a custom Ingredient.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported image type")

    image_bytes = await file.read()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    extracted = await extract_nutrition_from_image(b64, file.content_type or "image/jpeg")

    ingredient = Ingredient(
        source="custom",
        name=name or extracted.name or "Unnamed (Vision)",
        serving_size_desc=extracted.serving_size,
        calories=extracted.calories or 0,
        protein_g=extracted.protein_g or 0,
        fat_g=extracted.fat_g or 0,
        carbs_g=extracted.carbs_g or 0,
        sodium_mg=extracted.sodium_mg,
        cholesterol_mg=extracted.cholesterol_mg,
    )
    db.add(ingredient)
    await db.flush()
    return ingredient
