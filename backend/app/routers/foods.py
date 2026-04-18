"""
/foods — ingredient CRUD + USDA search + restaurant database lookup.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient
from app.schemas.schemas import IngredientCreate, IngredientRead, IngredientUpdate, USDASearchResult
from app.services.usda import search_usda, import_usda_food

router = APIRouter(prefix="/foods", tags=["Foods"])


# ── Local database search ─────────────────────────────────────────────────────

@router.get("/search", response_model=list[IngredientRead])
async def search_local_foods(
    q:      str = Query(..., min_length=1, description="Search term"),
    source: Optional[str] = Query(None, description="Filter: usda | restaurant | custom"),
    brand:  Optional[str] = Query(None, description="Filter by brand (e.g. Chipotle)"),
    limit:  int = Query(30, le=100),
    db:     AsyncSession = Depends(get_db),
):
    """
    Full-text style search of the local ingredients table.
    Searches name + brand case-insensitively.
    """
    stmt = select(Ingredient).where(
        or_(
            func.lower(Ingredient.name).contains(q.lower()),
            func.lower(Ingredient.brand).contains(q.lower()),
        )
    )
    if source:
        stmt = stmt.where(Ingredient.source == source)
    if brand:
        stmt = stmt.where(func.lower(Ingredient.brand) == brand.lower())

    # Personal foods come first, then custom recipes, then restaurant items, then USDA imports.
    source_rank = case(
        (Ingredient.source == "personal",   0),
        (Ingredient.source == "custom",     1),
        (Ingredient.source == "restaurant", 2),
        else_=3,
    )
    stmt = stmt.order_by(source_rank, Ingredient.name).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── Restaurant database (your CSV brands) ────────────────────────────────────

@router.get("/restaurant", response_model=list[IngredientRead])
async def list_restaurant_foods(
    brand: Optional[str] = Query(None, description="Chipotle | Cactus Club | Pokerrito"),
    db:    AsyncSession = Depends(get_db),
):
    """Returns all restaurant items, optionally filtered by brand."""
    stmt = select(Ingredient).where(Ingredient.source == "restaurant")
    if brand:
        stmt = stmt.where(func.lower(Ingredient.brand) == brand.lower())
    stmt = stmt.order_by(Ingredient.brand, Ingredient.name)
    result = await db.execute(stmt)
    return result.scalars().all()


# ── USDA FoodData Central ────────────────────────────────────────────────────

@router.get("/usda/search", response_model=list[USDASearchResult])
async def usda_search(
    q:     str = Query(..., min_length=2),
    limit: int = Query(10, le=25),
):
    """
    Proxy the USDA FoodData Central search API.
    Results are NOT automatically saved — use POST /foods/usda/{fdc_id}/import.
    """
    return await search_usda(q, limit)


@router.post("/usda/{fdc_id}/import", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def import_usda(
    fdc_id: int,
    db:     AsyncSession = Depends(get_db),
):
    """
    Fetch a USDA food by FDC ID and persist it to the local ingredients table.
    Idempotent — returns existing row if already imported.
    """
    # Check if already imported
    existing = await db.execute(select(Ingredient).where(Ingredient.usda_fdc_id == fdc_id))
    if row := existing.scalar_one_or_none():
        return row

    ingredient = await import_usda_food(fdc_id)
    db.add(ingredient)
    await db.flush()
    return ingredient


# ── Manual CRUD ───────────────────────────────────────────────────────────────

@router.post("/", response_model=IngredientRead, status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    body: IngredientCreate,
    db:   AsyncSession = Depends(get_db),
):
    """Manually create a custom ingredient (e.g. from a nutrition label you read yourself)."""
    ingredient = Ingredient(**body.model_dump())
    db.add(ingredient)
    await db.flush()
    return ingredient


@router.get("/{ingredient_id}", response_model=IngredientRead)
async def get_ingredient(ingredient_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return row


@router.patch("/{ingredient_id}", response_model=IngredientRead)
async def update_ingredient(
    ingredient_id: str,
    body: IngredientUpdate,
    db:   AsyncSession = Depends(get_db),
):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(row, field, val)
    await db.flush()
    return row


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingredient(ingredient_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Ingredient, ingredient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    await db.delete(row)
