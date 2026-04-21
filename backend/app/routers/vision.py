"""
/vision — upload a photo of a nutrition label (+ optional package/ingredients photo).
Claude extracts macros and returns them as JSON for review before saving.
"""
import base64
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient
from app.schemas.schemas import VisionExtractResponse, IngredientRead
from app.services.vision_ocr import extract_nutrition_from_images

router = APIRouter(prefix="/vision", tags=["Vision / OCR"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic"}


def _read_image(file: UploadFile, raw_bytes: bytes) -> tuple[str, str]:
    """Return (base64_data, mime_type) for an uploaded image file."""
    mime = file.content_type or "image/jpeg"
    return base64.b64encode(raw_bytes).decode("utf-8"), mime


@router.post("/extract", response_model=VisionExtractResponse)
async def extract_from_image(
    file:  UploadFile          = File(..., description="Nutrition facts label photo"),
    file2: Optional[UploadFile] = File(None, description="Front of package / ingredients list (optional)"),
):
    """
    Upload 1–2 photos. Returns structured macro data extracted by Claude.
    Does NOT save to DB — review the result first, then POST to /foods/ or /meals/.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{file.content_type}'. Use JPEG, PNG, or WebP.",
        )

    images = []
    raw1 = await file.read()
    if len(raw1) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image 1 too large (max 20 MB)")
    images.append(_read_image(file, raw1))

    if file2 and file2.filename:
        if file2.content_type not in ALLOWED_MIME:
            raise HTTPException(status_code=415, detail=f"Image 2 unsupported type '{file2.content_type}'.")
        raw2 = await file2.read()
        if len(raw2) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Image 2 too large (max 20 MB)")
        images.append(_read_image(file2, raw2))

    return await extract_nutrition_from_images(images)


@router.post("/extract-and-save", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def extract_and_save(
    file:  UploadFile           = File(...),
    file2: Optional[UploadFile] = File(None, description="Front of package / ingredients list (optional)"),
    name:  Optional[str]        = Form(None, description="Override the extracted name"),
    db:    AsyncSession         = Depends(get_db),
):
    """
    Extract macros from 1–2 images AND immediately save as a custom Ingredient.
    serving_size_g is extracted from the label and stored.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="Unsupported image type")

    images = []
    raw1 = await file.read()
    images.append(_read_image(file, raw1))

    if file2 and file2.filename:
        raw2 = await file2.read()
        images.append(_read_image(file2, raw2))

    extracted = await extract_nutrition_from_images(images)

    ingredient = Ingredient(
        source="custom",
        name=name or extracted.name or "Unnamed (Vision)",
        serving_size_desc=extracted.serving_size,
        serving_size_g=extracted.serving_size_g,
        calories=extracted.calories or 0,
        protein_g=extracted.protein_g or 0,
        fat_g=extracted.fat_g or 0,
        sat_fat_g=extracted.sat_fat_g,
        trans_fat_g=extracted.trans_fat_g,
        carbs_g=extracted.carbs_g or 0,
        fiber_g=extracted.fiber_g,
        sugar_g=extracted.sugar_g,
        added_sugar_g=extracted.added_sugar_g,
        sodium_mg=extracted.sodium_mg,
        cholesterol_mg=extracted.cholesterol_mg,
        potassium_mg=extracted.potassium_mg,
        calcium_mg=extracted.calcium_mg,
        iron_mg=extracted.iron_mg,
        vitamin_d_mcg=extracted.vitamin_d_mcg,
    )
    db.add(ingredient)
    await db.flush()
    return ingredient
