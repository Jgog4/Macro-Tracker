"""
/meals — log food entries, retrieve daily diary, get summary.

Key design: meal_number is auto-incremented per user per day.
A "meal" groups items logged within the same eating occasion.
The client POSTs items and either specifies meal_number or asks the server
to open a new meal (meal_number=None → auto-increment).
"""
from datetime import date as date_type, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import MealLog, MealLogItem, Ingredient, Recipe, DailyTarget, User
from app.schemas.schemas import (
    MealLogCreate, MealLogRead, MealLogItemRead, MealLogItemUpdate,
    DailyTargetCreate, DailyTargetRead, DailySummaryRead, MacroStat,
)

router = APIRouter(prefix="/meals", tags=["Meals"])

# ── Hardcoded single-user shortcut ────────────────────────────────────────────
# Replace with JWT lookup when multi-user support is needed.
DEFAULT_USER_EMAIL = "jesse@macro.app"


async def _get_or_create_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=DEFAULT_USER_EMAIL, name="Jesse")
        db.add(user)
        await db.flush()
    return user


async def _next_meal_number(db: AsyncSession, user_id: str, log_date: date_type) -> int:
    result = await db.execute(
        select(func.max(MealLog.meal_number)).where(
            MealLog.user_id == user_id,
            MealLog.log_date == log_date,
        )
    )
    current_max = result.scalar()
    return (current_max or 0) + 1


def _scale_macros(item: Ingredient | Recipe, qty_g: float) -> dict:
    """
    Scale macros proportionally to quantity consumed.
    For Ingredient: divide qty_g by serving_size_g to get multiplier.
    For Recipe:     divide qty_g by serving_size_g (or total_weight_g).
    """
    if isinstance(item, Ingredient):
        base_g = item.serving_size_g or qty_g   # if serving unknown, treat qty as full serving
    else:
        base_g = item.serving_size_g or item.total_weight_g or qty_g

    ratio = qty_g / base_g if base_g else 1.0

    return {
        "calories":       round((item.calories       or 0) * ratio, 2),
        "protein_g":      round((item.protein_g      or 0) * ratio, 2),
        "fat_g":          round((item.fat_g          or 0) * ratio, 2),
        "carbs_g":        round((item.carbs_g        or 0) * ratio, 2),
        "sodium_mg":      round((item.sodium_mg      or 0) * ratio, 2),
        "cholesterol_mg": round((item.cholesterol_mg or 0) * ratio, 2),
    }


# ── POST /meals — log food to a meal ─────────────────────────────────────────

@router.post("/", response_model=MealLogRead, status_code=status.HTTP_201_CREATED)
async def log_food(body: MealLogCreate, db: AsyncSession = Depends(get_db)):
    """
    Log one or more food items to a meal.
    • Omit meal_number → opens a NEW meal (auto-incremented).
    • Supply meal_number → appends to an existing meal for that day.
    """
    user = await _get_or_create_user(db)
    log_date = body.log_date or date_type.today()

    # Resolve meal_number
    if body.meal_number is None:
        meal_number = await _next_meal_number(db, user.id, log_date)
    else:
        meal_number = body.meal_number

    # Get or create the MealLog row
    result = await db.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id, MealLog.log_date == log_date, MealLog.meal_number == meal_number)
        .options(selectinload(MealLog.items))
    )
    meal = result.scalar_one_or_none()
    if not meal:
        meal = MealLog(user_id=user.id, log_date=log_date, meal_number=meal_number, logged_at=logged_at)
        db.add(meal)
        await db.flush()

    # Resolve logged_at timestamp (use client-supplied time or fall back to now)
    logged_at = body.logged_at or datetime.now(timezone.utc)

    # Add each item
    for item_body in body.items:
        if not item_body.ingredient_id and not item_body.recipe_id:
            raise HTTPException(status_code=400, detail="Each item needs ingredient_id or recipe_id")

        if item_body.ingredient_id:
            food = await db.get(Ingredient, item_body.ingredient_id)
            if not food:
                raise HTTPException(status_code=404, detail=f"Ingredient {item_body.ingredient_id} not found")
            macros = _scale_macros(food, item_body.quantity_g)
            display_name = f"{food.brand} — {food.name}" if food.brand else food.name
            log_item = MealLogItem(
                meal_log_id=meal.id,
                ingredient_id=food.id,
                display_name=display_name,
                quantity_g=item_body.quantity_g,
                logged_at=logged_at,
                **macros,
            )
        else:
            recipe = await db.get(Recipe, item_body.recipe_id)
            if not recipe:
                raise HTTPException(status_code=404, detail=f"Recipe {item_body.recipe_id} not found")
            macros = _scale_macros(recipe, item_body.quantity_g)
            log_item = MealLogItem(
                meal_log_id=meal.id,
                recipe_id=recipe.id,
                display_name=recipe.name,
                quantity_g=item_body.quantity_g,
                logged_at=logged_at,
                **macros,
            )

        db.add(log_item)

    # Refresh meal totals
    await db.flush()
    item_result = await db.execute(select(MealLogItem).where(MealLogItem.meal_log_id == meal.id))
    all_items = item_result.scalars().all()
    meal.total_calories       = round(sum(i.calories       for i in all_items), 2)
    meal.total_protein_g      = round(sum(i.protein_g      for i in all_items), 2)
    meal.total_fat_g          = round(sum(i.fat_g          for i in all_items), 2)
    meal.total_carbs_g        = round(sum(i.carbs_g        for i in all_items), 2)
    meal.total_sodium_mg      = round(sum(i.sodium_mg      for i in all_items), 2)
    meal.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in all_items), 2)
    await db.flush()

    # Reload with items for response
    await db.refresh(meal)
    result2 = await db.execute(
        select(MealLog)
        .where(MealLog.id == meal.id)
        .options(selectinload(MealLog.items))
    )
    return result2.scalar_one()


# ── GET /meals/today — today's diary ─────────────────────────────────────────

@router.get("/today", response_model=DailySummaryRead)
async def get_today_summary(db: AsyncSession = Depends(get_db)):
    return await get_daily_summary(date_type.today(), db)


@router.get("/day/{log_date}", response_model=DailySummaryRead)
async def get_daily_summary(
    log_date: date_type,
    db:       AsyncSession = Depends(get_db),
):
    """Full dashboard summary for a given date: targets, consumed, remaining, per-meal breakdown."""
    user = await _get_or_create_user(db)

    # Fetch targets (most recent on or before log_date)
    tgt_result = await db.execute(
        select(DailyTarget)
        .where(DailyTarget.user_id == user.id, DailyTarget.target_date <= log_date)
        .order_by(desc(DailyTarget.target_date))
        .limit(1)
    )
    target = tgt_result.scalar_one_or_none()
    # Defaults if no target row exists yet
    cal_t  = target.calories       if target else 3258.0
    pro_t  = target.protein_g      if target else 244.3
    fat_t  = target.fat_g          if target else 90.5
    carb_t = target.carbs_g        if target else 366.5
    sod_t  = target.sodium_mg      if target else 2300.0
    cho_t  = target.cholesterol_mg if target else 300.0

    # Fetch meals for the day
    meals_result = await db.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id, MealLog.log_date == log_date)
        .options(selectinload(MealLog.items))
        .order_by(MealLog.meal_number)
    )
    meals = meals_result.scalars().all()

    # Aggregate consumed
    cal_c  = sum(m.total_calories       for m in meals)
    pro_c  = sum(m.total_protein_g      for m in meals)
    fat_c  = sum(m.total_fat_g          for m in meals)
    carb_c = sum(m.total_carbs_g        for m in meals)
    sod_c  = sum(m.total_sodium_mg      for m in meals)
    cho_c  = sum(m.total_cholesterol_mg for m in meals)

    def stat(consumed, target_val) -> MacroStat:
        remaining = max(0.0, target_val - consumed)
        pct = min(100.0, round((consumed / target_val * 100) if target_val else 0, 1))
        return MacroStat(consumed=round(consumed, 1), target=round(target_val, 1),
                         remaining=round(remaining, 1), pct=pct)

    return DailySummaryRead(
        log_date=log_date,
        energy=stat(cal_c, cal_t),
        protein=stat(pro_c, pro_t),
        fat=stat(fat_c, fat_t),
        net_carbs=stat(carb_c - 0, carb_t),   # TODO: subtract fiber when available
        sodium=stat(sod_c, sod_t),
        cholesterol=stat(cho_c, cho_t),
        meals=meals,
    )


# ── PATCH a meal log item (edit quantity / time) ──────────────────────────────

@router.patch("/items/{item_id}", response_model=MealLogItemRead)
async def update_log_item(
    item_id: str,
    body:    MealLogItemUpdate,
    db:      AsyncSession = Depends(get_db),
):
    """Update quantity_g and/or logged_at for an existing log item. Macros are recalculated."""
    item = await db.get(MealLogItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.quantity_g is not None and body.quantity_g != item.quantity_g:
        # Re-scale macros against the stored ingredient / recipe
        if item.ingredient_id:
            food = await db.get(Ingredient, item.ingredient_id)
            if food:
                macros = _scale_macros(food, body.quantity_g)
                item.quantity_g = body.quantity_g
                for k, v in macros.items():
                    setattr(item, k, v)
            else:
                item.quantity_g = body.quantity_g
        else:
            # Recipe: just update quantity (macro re-scale via recipe)
            recipe = await db.get(Recipe, item.recipe_id)
            if recipe:
                macros = _scale_macros(recipe, body.quantity_g)
                item.quantity_g = body.quantity_g
                for k, v in macros.items():
                    setattr(item, k, v)
            else:
                item.quantity_g = body.quantity_g

    if body.logged_at is not None:
        item.logged_at = body.logged_at

    await db.flush()

    # Recompute meal totals
    remaining = await db.execute(select(MealLogItem).where(MealLogItem.meal_log_id == item.meal_log_id))
    all_items = remaining.scalars().all()
    meal = await db.get(MealLog, item.meal_log_id)
    if meal:
        meal.total_calories       = round(sum(i.calories       for i in all_items), 2)
        meal.total_protein_g      = round(sum(i.protein_g      for i in all_items), 2)
        meal.total_fat_g          = round(sum(i.fat_g          for i in all_items), 2)
        meal.total_carbs_g        = round(sum(i.carbs_g        for i in all_items), 2)
        meal.total_sodium_mg      = round(sum(i.sodium_mg      for i in all_items), 2)
        meal.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in all_items), 2)

    await db.flush()
    await db.refresh(item)
    return item


# ── DELETE a meal log item ────────────────────────────────────────────────────

@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log_item(item_id: str, db: AsyncSession = Depends(get_db)):
    item = await db.get(MealLogItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    meal_id = item.meal_log_id
    await db.delete(item)
    await db.flush()

    # Recompute meal totals
    remaining = await db.execute(select(MealLogItem).where(MealLogItem.meal_log_id == meal_id))
    all_items = remaining.scalars().all()
    meal = await db.get(MealLog, meal_id)
    if meal:
        meal.total_calories       = round(sum(i.calories       for i in all_items), 2)
        meal.total_protein_g      = round(sum(i.protein_g      for i in all_items), 2)
        meal.total_fat_g          = round(sum(i.fat_g          for i in all_items), 2)
        meal.total_carbs_g        = round(sum(i.carbs_g        for i in all_items), 2)
        meal.total_sodium_mg      = round(sum(i.sodium_mg      for i in all_items), 2)
        meal.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in all_items), 2)


# ── Daily Targets ─────────────────────────────────────────────────────────────

@router.post("/targets", response_model=DailyTargetRead, status_code=status.HTTP_201_CREATED)
async def set_daily_target(body: DailyTargetCreate, db: AsyncSession = Depends(get_db)):
    """Set or update macro targets for a specific date."""
    user = await _get_or_create_user(db)
    existing = await db.execute(
        select(DailyTarget).where(DailyTarget.user_id == user.id, DailyTarget.target_date == body.target_date)
    )
    target = existing.scalar_one_or_none()
    if target:
        for field, val in body.model_dump().items():
            setattr(target, field, val)
    else:
        target = DailyTarget(user_id=user.id, **body.model_dump())
        db.add(target)
    await db.flush()
    return target


@router.get("/targets/latest", response_model=DailyTargetRead)
async def get_latest_target(db: AsyncSession = Depends(get_db)):
    """Get the most recently set macro targets."""
    user = await _get_or_create_user(db)
    result = await db.execute(
        select(DailyTarget).where(DailyTarget.user_id == user.id)
        .order_by(desc(DailyTarget.target_date)).limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No targets set yet. POST /meals/targets first.")
    return row
