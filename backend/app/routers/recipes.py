"""
/recipes — create and manage custom blended recipes (Turkey & Rice, Cream of Rice, etc.)

The recipe engine scales constituent ingredient macros by gram weight
and stores computed totals on the Recipe row for fast reads.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import (
    Ingredient, MealLog, MealLogItem, Recipe, RecipeImportLog, RecipeIngredient,
)
from app.schemas.schemas import RecipeCreate, RecipeRead, RecipeUpdate
from app.services.recipe_math import compute_recipe_totals

router = APIRouter(prefix="/recipes", tags=["Recipes"])


def _compute_recipe_totals(ingredients_with_qty: list[tuple]) -> dict:
    """Backward-compatible name used by existing scripts and import code."""
    return compute_recipe_totals(ingredients_with_qty)


async def _attach_import_metadata(db: AsyncSession, recipes: list[Recipe]) -> None:
    """Expose importer provenance without a duplicate Recipe database column."""
    if not recipes:
        return
    recipe_ids = [recipe.id for recipe in recipes]
    imported_ids = set((await db.execute(
        select(RecipeImportLog.recipe_id).where(
            RecipeImportLog.recipe_id.in_(recipe_ids)
        )
    )).scalars())
    for recipe in recipes:
        # source_url covers imports saved before import history was linked.
        recipe.is_imported = recipe.id in imported_ids or bool(recipe.source_url)


@router.post("/", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
async def create_recipe(body: RecipeCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a custom recipe blend. Example:

    POST /recipes
    {
      "name": "Turkey & Rice",
      "serving_size_g": 495,
      "ingredients": [
        {"ingredient_id": "<turkey-uuid>", "quantity_g": 200},
        {"ingredient_id": "<rice-uuid>",   "quantity_g": 295}
      ]
    }
    """
    recipe = Recipe(name=body.name, description=body.description, serving_size_g=body.serving_size_g, num_servings=max(1, body.num_servings or 1))
    db.add(recipe)
    await db.flush()

    pairs: list[tuple[Ingredient, float]] = []
    for item in body.ingredients:
        ing = await db.get(Ingredient, item.ingredient_id)
        if not ing:
            raise HTTPException(status_code=404, detail=f"Ingredient {item.ingredient_id} not found")
        ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id,
                              quantity_g=item.quantity_g, fat_retention=item.fat_retention)
        db.add(ri)
        pairs.append((ing, item.quantity_g, item.fat_retention))

    totals = _compute_recipe_totals(pairs)
    for field, val in totals.items():
        setattr(recipe, field, val)

    await db.flush()
    # Reload with nested relationships for response
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe.id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    row = result.scalar_one()
    await _attach_import_metadata(db, [row])
    return row


@router.get("/", response_model=list[RecipeRead])
async def list_recipes(
    q:  Optional[str] = Query(None, description="Search term for recipe name"),
    db: AsyncSession  = Depends(get_db),
):
    stmt = select(Recipe).options(
        selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient)
    )
    if q:
        words = [w for w in q.lower().split() if w]
        for word in words:
            stmt = stmt.where(func.lower(Recipe.name).contains(word))
    stmt = stmt.order_by(Recipe.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    # Recipes are logged through mt_meal_log_items.recipe_id, not ingredient_id,
    # so their usage lives in a different column than a food's. Attach it here
    # so the client can rank recipes and foods on the same recency scale —
    # without it, a recipe eaten every morning sorts below foods never eaten.
    if rows:
        usage = await db.execute(
            select(
                MealLogItem.recipe_id,
                func.count().label("log_count"),
                func.max(MealLog.log_date).label("last_logged"),
            )
            .join(MealLog, MealLog.id == MealLogItem.meal_log_id)
            .where(MealLogItem.recipe_id.in_([r.id for r in rows]))
            .group_by(MealLogItem.recipe_id)
        )
        by_id = {u.recipe_id: u for u in usage}
        for r in rows:
            u = by_id.get(r.id)
            r.last_logged = u.last_logged if u else None
            r.log_count   = u.log_count if u else 0
    await _attach_import_metadata(db, rows)
    return rows


@router.get("/{recipe_id}", response_model=RecipeRead)
async def get_recipe(recipe_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await _attach_import_metadata(db, [row])
    return row


@router.patch("/{recipe_id}", response_model=RecipeRead)
async def update_recipe(recipe_id: str, body: RecipeUpdate, db: AsyncSession = Depends(get_db)):
    """
    Partially update a recipe. If ingredients are provided, the full list is replaced
    and totals are recomputed. serving_size_g stores the cooked/final weight.
    """
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    recipe = result.scalar_one_or_none()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if body.name is not None:
        recipe.name = body.name
    if body.description is not None:
        recipe.description = body.description
    if body.serving_size_g is not None:
        recipe.serving_size_g = body.serving_size_g
    if body.num_servings is not None:
        recipe.num_servings = max(1, body.num_servings)

    if body.ingredients is not None:
        # Delete existing ingredient rows
        for ri in list(recipe.ingredients):
            await db.delete(ri)
        await db.flush()

        # Add new ones and recompute totals
        pairs: list[tuple[Ingredient, float]] = []
        for item in body.ingredients:
            ing = await db.get(Ingredient, item.ingredient_id)
            if not ing:
                raise HTTPException(status_code=404, detail=f"Ingredient {item.ingredient_id} not found")
            ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id,
                                  quantity_g=item.quantity_g, fat_retention=item.fat_retention)
            db.add(ri)
            pairs.append((ing, item.quantity_g, item.fat_retention))

        totals = _compute_recipe_totals(pairs)
        for field, val in totals.items():
            setattr(recipe, field, val)

    await db.flush()
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    row = result.scalar_one()
    await _attach_import_metadata(db, [row])
    return row


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(recipe_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Recipe, recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await db.delete(row)
