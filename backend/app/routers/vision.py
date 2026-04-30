"""
/vision — upload a photo of a nutrition label (+ optional package/ingredients photo).
Claude extracts macros and returns them as JSON for review before saving.
"""
import base64
import httpx
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient
from app.schemas.schemas import VisionExtractResponse, IngredientRead
from app.services.vision_ocr import (
    extract_nutrition_from_images,
    estimate_from_ingredient_images,
    analyze_recipe_url,
)
from pydantic import BaseModel as _BaseModel

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

    # Map all VisionExtractResponse fields that have matching Ingredient columns
    from app.models.models import Ingredient as IngredientModel
    valid_cols = {c.key for c in IngredientModel.__table__.columns}
    extracted_dict = extracted.model_dump(exclude={"confidence", "raw_text", "serving_size", "name"})
    nutrient_kwargs = {k: v for k, v in extracted_dict.items() if k in valid_cols and v is not None}

    ingredient = Ingredient(
        source="custom",
        name=name or extracted.name or "Unnamed (Vision)",
        serving_size_desc=extracted.serving_size,
        serving_size_g=extracted.serving_size_g,
        calories=extracted.calories or 0,
        protein_g=extracted.protein_g or 0,
        fat_g=extracted.fat_g or 0,
        carbs_g=extracted.carbs_g or 0,
        **{k: v for k, v in nutrient_kwargs.items()
           if k not in ("calories", "protein_g", "fat_g", "carbs_g", "serving_size_g")},
    )
    db.add(ingredient)
    await db.flush()
    return ingredient


# ── POST /vision/estimate-from-ingredients — ingredient list photo ────────────

@router.post(
    "/estimate-from-ingredients",
    response_model=IngredientRead,
    status_code=status.HTTP_201_CREATED,
)
async def estimate_from_ingredients(
    files: List[UploadFile]     = File(..., description="One or more photos of ingredient lists / package backs / meal screenshots"),
    name:  Optional[str]        = Form(None, description="Override the inferred name"),
    db:    AsyncSession         = Depends(get_db),
):
    """
    Upload 1+ photos of an ingredient list, package back, or meal-tracking
    screenshot. Claude ESTIMATES the nutrition (not reads a label).
    Saves as a personal Ingredient and returns it.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 images allowed.")

    images = []
    for f in files:
        raw = await f.read()
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Image '{f.filename}' too large (max 20 MB)")
        images.append((base64.b64encode(raw).decode(), f.content_type or "image/jpeg"))

    estimated = await estimate_from_ingredient_images(images)
    if estimated.confidence == 0.0:
        raise HTTPException(
            status_code=502,
            detail="Could not parse nutrition data from the image(s). "
                   "Please ensure the photos clearly show an ingredient list or nutrition label."
        )

    from app.models.models import Ingredient as IngredientModel
    valid_cols    = {c.key for c in IngredientModel.__table__.columns}
    estimated_dict = estimated.model_dump(exclude={"confidence", "raw_text", "serving_size", "name"})
    nutrient_kwargs = {k: v for k, v in estimated_dict.items() if k in valid_cols and v is not None}

    ingredient = Ingredient(
        source="personal",
        name=name or estimated.name or "Unnamed (Estimate)",
        serving_size_desc=estimated.serving_size,
        serving_size_g=estimated.serving_size_g,
        calories=estimated.calories or 0,
        protein_g=estimated.protein_g or 0,
        fat_g=estimated.fat_g or 0,
        carbs_g=estimated.carbs_g or 0,
        **{k: v for k, v in nutrient_kwargs.items()
           if k not in ("calories", "protein_g", "fat_g", "carbs_g", "serving_size_g")},
    )
    db.add(ingredient)
    await db.flush()
    return ingredient


# ── POST /vision/from-url — recipe URL analysis ───────────────────────────────

class _UrlRequest(_BaseModel):
    url:              Optional[str] = None   # fetch a URL
    ingredients_text: Optional[str] = None  # or paste raw ingredient text
    name:             Optional[str] = None


@router.post(
    "/from-url",
    response_model=IngredientRead,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_from_url(
    body: _UrlRequest,
    db:   AsyncSession = Depends(get_db),
):
    """
    Estimate per-serving nutrition from either:
      • a recipe URL  (body.url)
      • pasted ingredient text (body.ingredients_text)
    Saves as a personal Ingredient and returns it.
    """
    from app.services.vision_ocr import _call_claude_text, RECIPE_URL_PROMPT
    import httpx as _httpx

    if body.ingredients_text:
        # Direct text path — no URL fetch needed
        user_msg  = (
            f"Please estimate the nutrition per serving for this recipe.\n\n"
            f"{body.ingredients_text.strip()}"
            + (f"\n\nFood name: {body.name}" if body.name else "")
        )
        estimated = await _call_claude_text(RECIPE_URL_PROMPT, user_msg)
        if estimated.confidence == 0.0:
            raise HTTPException(
                status_code=502,
                detail="Could not parse nutrition data from the ingredient list. "
                       "Please make sure the list clearly states quantities and ingredients, "
                       "and try again."
            )
        if body.name and not estimated.name:
            estimated.name = body.name

    elif body.url:
        try:
            estimated = await analyze_recipe_url(body.url, body.name)
        except _httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Could not fetch URL (HTTP {e.response.status_code}). "
                       "The site may be blocking automated requests — "
                       "try pasting the ingredient list as text instead."
            )
        except _httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach URL: {e}. Try pasting the ingredient list as text instead."
            )
        if estimated.confidence == 0.0:
            raise HTTPException(
                status_code=502,
                detail="Could not parse nutrition data from the recipe page. "
                       "Try pasting the ingredient list as text instead."
            )
    else:
        raise HTTPException(status_code=400, detail="Provide either url or ingredients_text.")

    from app.models.models import Ingredient as IngredientModel
    valid_cols    = {c.key for c in IngredientModel.__table__.columns}
    estimated_dict = estimated.model_dump(exclude={"confidence", "raw_text", "serving_size", "name"})
    nutrient_kwargs = {k: v for k, v in estimated_dict.items() if k in valid_cols and v is not None}

    ingredient = Ingredient(
        source="personal",
        name=body.name or estimated.name or "Recipe (URL)",
        serving_size_desc=estimated.serving_size,
        serving_size_g=estimated.serving_size_g,
        calories=estimated.calories or 0,
        protein_g=estimated.protein_g or 0,
        fat_g=estimated.fat_g or 0,
        carbs_g=estimated.carbs_g or 0,
        **{k: v for k, v in nutrient_kwargs.items()
           if k not in ("calories", "protein_g", "fat_g", "carbs_g", "serving_size_g")},
    )
    db.add(ingredient)
    await db.flush()
    return ingredient


# ── GET /vision/barcode/{barcode} — Open Food Facts lookup ────────────────────

from pydantic import BaseModel as _PydanticBase

class BarcodeResult(_PydanticBase):
    name:              str
    brand:             Optional[str]   = None
    serving_size_desc: Optional[str]   = None
    serving_size_g:    Optional[float] = None
    calories:          float           = 0.0
    protein_g:         float           = 0.0
    fat_g:             float           = 0.0
    carbs_g:           float           = 0.0
    sat_fat_g:         Optional[float] = None
    trans_fat_g:       Optional[float] = None
    fiber_g:           Optional[float] = None
    sugar_g:           Optional[float] = None
    sodium_mg:         Optional[float] = None
    cholesterol_mg:    Optional[float] = None
    potassium_mg:      Optional[float] = None


@router.get("/barcode/{barcode}", response_model=BarcodeResult)
async def lookup_barcode(barcode: str):
    """
    Query Open Food Facts for a UPC/EAN barcode.
    Returns parsed nutrition data for review — does NOT save to DB.
    Call POST /foods/ to save after the user confirms.
    """
    off_url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(off_url, headers={"User-Agent": "MacroTrackerApp/1.0"})
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Open Food Facts request failed: {e}")

    if data.get("status") != 1:
        raise HTTPException(status_code=404, detail="Product not found in Open Food Facts database.")

    p = data.get("product", {})
    n = p.get("nutriments", {})

    name  = (p.get("product_name_en") or p.get("product_name") or "Unknown Product").strip()
    brand = (p.get("brands") or "").split(",")[0].strip() or None

    serving_desc: Optional[str]   = p.get("serving_size") or None
    serving_g:    Optional[float] = None
    if p.get("serving_quantity"):
        try:
            serving_g = float(p["serving_quantity"])
        except (ValueError, TypeError):
            pass

    base = serving_g or 100.0

    def _n100(key: str) -> Optional[float]:
        v = n.get(f"{key}_100g")
        return float(v) if v is not None else None

    def _scaled(key: str) -> Optional[float]:
        v = _n100(key)
        if v is None:
            return None
        return round(v * base / 100.0, 3)

    cal = _scaled("energy-kcal")
    if cal is None:
        kj = _scaled("energy")
        if kj is not None:
            cal = round(kj / 4.184, 1)

    # Sodium in OFF = g/100g → convert to mg
    sodium_scaled = _scaled("sodium")
    sodium_mg = round(sodium_scaled * 1000, 1) if sodium_scaled is not None else None

    return BarcodeResult(
        name=f"{brand} {name}".strip() if brand else name,
        brand=brand,
        serving_size_desc=serving_desc,
        serving_size_g=serving_g,
        calories=cal or 0.0,
        protein_g=_scaled("proteins") or 0.0,
        fat_g=_scaled("fat") or 0.0,
        carbs_g=_scaled("carbohydrates") or 0.0,
        sat_fat_g=_scaled("saturated-fat"),
        trans_fat_g=_scaled("trans-fat"),
        fiber_g=_scaled("fiber"),
        sugar_g=_scaled("sugars"),
        sodium_mg=sodium_mg,
        cholesterol_mg=_scaled("cholesterol"),
        potassium_mg=_scaled("potassium"),
    )
