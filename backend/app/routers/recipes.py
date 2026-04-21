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
from app.models.models import Ingredient, Recipe, RecipeIngredient
from app.schemas.schemas import RecipeCreate, RecipeRead, RecipeUpdate

router = APIRouter(prefix="/recipes", tags=["Recipes"])


def _compute_recipe_totals(ingredients_with_qty: list[tuple[Ingredient, float]]) -> dict:
    """
    Sum macros across all (ingredient, quantity_g) pairs.
    Each ingredient stores macros *per serving* — we scale by qty/serving_size_g.
    """
    totals = dict(calories=0.0, protein_g=0.0, fat_g=0.0, carbs_g=0.0,
                  sodium_mg=0.0, cholesterol_mg=0.0, total_weight_g=0.0)
    for ing, qty_g in ingredients_with_qty:
        base_g = ing.serving_size_g or qty_g
        ratio  = qty_g / base_g if base_g else 1.0
        totals["calories"]       += (ing.calories       or 0) * ratio
        totals["protein_g"]      += (ing.protein_g      or 0) * ratio
        totals["fat_g"]          += (ing.fat_g          or 0) * ratio
        totals["carbs_g"]        += (ing.carbs_g        or 0) * ratio
        totals["sodium_mg"]      += (ing.sodium_mg      or 0) * ratio
        totals["cholesterol_mg"] += (ing.cholesterol_mg or 0) * ratio
        totals["total_weight_g"] += qty_g
    return {k: round(v, 2) for k, v in totals.items()}


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
    recipe = Recipe(name=body.name, description=body.description, serving_size_g=body.serving_size_g)
    db.add(recipe)
    await db.flush()

    pairs: list[tuple[Ingredient, float]] = []
    for item in body.ingredients:
        ing = await db.get(Ingredient, item.ingredient_id)
        if not ing:
            raise HTTPException(status_code=404, detail=f"Ingredient {item.ingredient_id} not found")
        ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id, quantity_g=item.quantity_g)
        db.add(ri)
        pairs.append((ing, item.quantity_g))

    totals = _compute_recipe_totals(pairs)
    for field, val in totals.items():
        setattr(recipe, field, val)

    await db.flush()
    # Reload with nested relationships for response
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe.id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    return result.scalar_one()


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
    return result.scalars().all()


@router.get("/{recipe_id}", response_model=RecipeRead)
async def get_recipe(recipe_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
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
            ri = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ing.id, quantity_g=item.quantity_g)
            db.add(ri)
            pairs.append((ing, item.quantity_g))

        totals = _compute_recipe_totals(pairs)
        for field, val in totals.items():
            setattr(recipe, field, val)

    await db.flush()
    result = await db.execute(
        select(Recipe).where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    )
    return result.scalar_one()


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(recipe_id: str, db: AsyncSession = Depends(get_db)):
    row = await db.get(Recipe, recipe_id)
    if not row:
        raise HTTPException(status_code=404, detail="Recipe not found")
    await db.delete(row)
