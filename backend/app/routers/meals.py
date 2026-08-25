"""
/meals — log food entries, retrieve daily diary, get summary, micronutrients.

Key design: meal_number is auto-incremented per user per day.
A "meal" groups items logged within the same eating occasion.
The client POSTs items and either specifies meal_number or asks the server
to open a new meal (meal_number=None → auto-increment).

Recipe sub-ingredient snapshots
────────────────────────────────
When a recipe is logged, every ingredient in that recipe is snapshotted into
mt_meal_log_item_components (scaled to the logged quantity). This lets future
analysis reference real foods (e.g. "350g of white rice") even if the recipe
is later edited or deleted.

Micronutrient endpoint
──────────────────────
GET /meals/micronutrients?start=yyyy-MM-dd&end=yyyy-MM-dd

Aggregates all micronutrients from:
  1. Direct ingredient items  → scaled by (quantity_g / serving_size_g)
  2. Recipe item components   → already stored pre-scaled; scaled again by
                                (component.quantity_g / ingredient.serving_size_g)
"""
from datetime import date as date_type, datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import (
    MealLog, MealLogItem, MealLogItemComponent,
    Ingredient, Recipe, RecipeIngredient,
    DailyTarget, User,
)
from app.schemas.schemas import (
    MealLogCreate, MealLogRead, MealLogItemRead, MealLogItemUpdate, MealLogItemComponentUpdate, MealCopyRequest,
    DailyTargetCreate, DailyTargetRead, DailySummaryRead, MacroStat,
    MicronutrientSummaryRead, MicronutrientTotals,
)

router = APIRouter(prefix="/meals", tags=["Meals"])

# ── Hardcoded single-user shortcut ────────────────────────────────────────────
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
    """Scale macros proportionally to quantity consumed."""
    if isinstance(item, Ingredient):
        base_g = item.serving_size_g or 100.0  # null serving_size_g → macros stored per 100g
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


async def _recalculate_meal_totals(db: AsyncSession, meal_id: str) -> None:
    """Refresh the cached totals stored on a meal after one of its items changes."""
    result = await db.execute(select(MealLogItem).where(MealLogItem.meal_log_id == meal_id))
    items = result.scalars().all()
    meal = await db.get(MealLog, meal_id)
    if not meal:
        return
    meal.total_calories       = round(sum(i.calories       for i in items), 2)
    meal.total_protein_g      = round(sum(i.protein_g      for i in items), 2)
    meal.total_fat_g          = round(sum(i.fat_g          for i in items), 2)
    meal.total_carbs_g        = round(sum(i.carbs_g        for i in items), 2)
    meal.total_sodium_mg      = round(sum(i.sodium_mg      for i in items), 2)
    meal.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in items), 2)


async def _recalculate_recipe_item_from_components(db: AsyncSession, item: MealLogItem) -> None:
    """Rebuild a logged recipe's macro snapshot from its per-day component snapshots."""
    result = await db.execute(
        select(MealLogItemComponent, Ingredient)
        .outerjoin(Ingredient, MealLogItemComponent.ingredient_id == Ingredient.id)
        .where(MealLogItemComponent.meal_log_item_id == item.id)
    )
    totals = {field: 0.0 for field in _SNAPSHOT_FIELDS}
    total_weight_g = 0.0
    for component, ingredient in result.all():
        total_weight_g += component.quantity_g
        # Components normally retain an ingredient id. If its library food was
        # deleted later, retain its existing historical contribution rather than
        # inventing replacement nutrition data.
        if not ingredient:
            continue
        macros = _scale_macros(ingredient, component.quantity_g)
        for field, value in macros.items():
            totals[field] += value

    item.quantity_g = round(total_weight_g, 2)
    for field, value in totals.items():
        setattr(item, field, round(value, 2))


def _add_micro(totals: dict, field: str, value: Optional[float]) -> None:
    """Add a micronutrient value to the running totals dict (handles None cleanly)."""
    if value is not None:
        totals[field] = round((totals.get(field) or 0.0) + value, 6)


# Fields snapshotted directly on MealLogItem — use those values, not ingredient scaling
_SNAPSHOT_FIELDS = {"calories", "protein_g", "fat_g", "carbs_g", "sodium_mg", "cholesterol_mg"}

# All micronutrient field names on Ingredient (for iteration)
# Snapshot fields are excluded here; they're summed from MealLogItem directly.
_MICRO_FIELDS = [
    # Macros (non-snapshotted ones still come from ingredient scaling)
    "fiber_g", "sugar_g", "sat_fat_g", "trans_fat_g", "potassium_mg",
    # Vitamins
    "vitamin_a_mcg", "vitamin_c_mg", "vitamin_d_mcg", "vitamin_e_mg", "vitamin_k_mcg",
    "thiamine_mg", "riboflavin_mg", "niacin_mg", "pantothenic_acid_mg", "pyridoxine_mg",
    "cobalamin_mcg", "biotin_mcg", "folate_mcg", "choline_mg", "retinol_mcg",
    "alpha_carotene_mcg", "beta_carotene_mcg", "beta_cryptoxanthin_mcg",
    "lutein_zeaxanthin_mcg", "lycopene_mcg",
    "beta_tocopherol_mg", "delta_tocopherol_mg", "gamma_tocopherol_mg",
    # Minerals
    "calcium_mg", "iron_mg", "magnesium_mg", "phosphorus_mg", "zinc_mg",
    "copper_mg", "manganese_mg", "selenium_mcg", "chromium_mcg",
    "iodine_mcg", "molybdenum_mcg", "fluoride_mg",
    # Amino acids
    "alanine_g", "arginine_g", "aspartic_acid_g", "cystine_g", "glutamic_acid_g",
    "glycine_g", "histidine_g", "hydroxyproline_g", "isoleucine_g", "leucine_g",
    "lysine_g", "methionine_g", "phenylalanine_g", "proline_g", "serine_g",
    "threonine_g", "tryptophan_g", "tyrosine_g", "valine_g",
    # Fatty acids
    "monounsaturated_fat_g", "polyunsaturated_fat_g",
    "omega3_ala_g", "omega3_dha_g", "omega3_epa_g",
    "omega6_aa_g", "omega6_la_g", "phytosterol_mg",
    # Carb details & other
    "soluble_fiber_g", "insoluble_fiber_g",
    "fructose_g", "galactose_g", "glucose_g", "lactose_g", "maltose_g", "sucrose_g",
    "oxalate_mg", "phytate_mg", "caffeine_mg",
    "water_g", "ash_g", "alcohol_g", "beta_hydroxybutyrate_g",
]


def _accumulate_ingredient_micros(
    totals: dict,
    ingredient: Ingredient,
    quantity_g: float,
) -> None:
    """Scale ingredient micronutrients by quantity and add to totals."""
    base_g = ingredient.serving_size_g or 100.0  # null serving_size_g → micros stored per 100g
    ratio  = quantity_g / base_g if base_g else 1.0
    for field in _MICRO_FIELDS:
        raw = getattr(ingredient, field, None)
        if raw is not None:
            _add_micro(totals, field, raw * ratio)


# ── POST /meals — log food to a meal ─────────────────────────────────────────

@router.post("/", response_model=MealLogRead, status_code=status.HTTP_201_CREATED)
async def log_food(body: MealLogCreate, db: AsyncSession = Depends(get_db)):
    """
    Log one or more food items to a meal.
    • Omit meal_number → opens a NEW meal (auto-incremented).
    • Supply meal_number → appends to an existing meal for that day.
    • When a recipe is logged, its sub-ingredients are snapshotted into
      mt_meal_log_item_components for later micronutrient analysis.
    """
    user = await _get_or_create_user(db)
    log_date = body.log_date or date_type.today()

    if body.meal_number is None:
        meal_number = await _next_meal_number(db, user.id, log_date)
    else:
        meal_number = body.meal_number

    logged_at = body.logged_at or datetime.now(timezone.utc)

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
            db.add(log_item)

        else:
            # Load recipe with its ingredients so we can snapshot them
            recipe_result = await db.execute(
                select(Recipe)
                .where(Recipe.id == item_body.recipe_id)
                .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
            )
            recipe = recipe_result.scalar_one_or_none()
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
            await db.flush()   # need log_item.id for components

            # Snapshot sub-ingredients (scaled to logged quantity)
            base_g = recipe.serving_size_g or recipe.total_weight_g or item_body.quantity_g
            ratio  = item_body.quantity_g / base_g if base_g else 1.0

            for ri in recipe.ingredients:
                if ri.ingredient:
                    component = MealLogItemComponent(
                        meal_log_item_id=log_item.id,
                        ingredient_id=ri.ingredient.id,
                        ingredient_name=(
                            f"{ri.ingredient.brand} — {ri.ingredient.name}"
                            if ri.ingredient.brand else ri.ingredient.name
                        ),
                        quantity_g=round(ri.quantity_g * ratio, 2),
                    )
                    db.add(component)

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

    # Reload with items + components for response
    result2 = await db.execute(
        select(MealLog)
        .where(MealLog.id == meal.id)
        .options(
            selectinload(MealLog.items)
            .selectinload(MealLogItem.components)
        )
    )
    return result2.scalar_one()


# ── GET /meals/today ─────────────────────────────────────────────────────────

@router.get("/today", response_model=DailySummaryRead)
async def get_today_summary(db: AsyncSession = Depends(get_db)):
    return await get_daily_summary(date_type.today(), db)


@router.get("/day/{log_date}", response_model=DailySummaryRead)
async def get_daily_summary(
    log_date: date_type,
    db:       AsyncSession = Depends(get_db),
):
    """Full dashboard summary for a given date."""
    user = await _get_or_create_user(db)

    tgt_result = await db.execute(
        select(DailyTarget)
        .where(DailyTarget.user_id == user.id, DailyTarget.target_date <= log_date)
        .order_by(desc(DailyTarget.target_date))
        .limit(1)
    )
    target = tgt_result.scalar_one_or_none()
    cal_t  = target.calories       if target else 3258.0
    pro_t  = target.protein_g      if target else 244.3
    fat_t  = target.fat_g          if target else 90.5
    carb_t = target.carbs_g        if target else 366.5
    sod_t  = target.sodium_mg      if target else 2300.0
    cho_t  = target.cholesterol_mg if target else 300.0

    meals_result = await db.execute(
        select(MealLog)
        .where(MealLog.user_id == user.id, MealLog.log_date == log_date)
        .options(
            selectinload(MealLog.items)
            .selectinload(MealLogItem.components)
        )
        .order_by(MealLog.meal_number)
    )
    meals = meals_result.scalars().all()

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
        net_carbs=stat(carb_c, carb_t),
        sodium=stat(sod_c, sod_t),
        cholesterol=stat(cho_c, cho_t),
        meals=meals,
    )


# ── GET /meals/micronutrients — aggregate micronutrient totals ────────────────

@router.get("/micronutrients", response_model=MicronutrientSummaryRead)
async def get_micronutrients(
    start: date_type = Query(..., description="Start date (yyyy-MM-dd)"),
    end:   date_type = Query(..., description="End date inclusive (yyyy-MM-dd)"),
    db:    AsyncSession = Depends(get_db),
):
    """
    Aggregate all micronutrients for a date range.

    Sources:
    - Direct ingredient items:  scaled by qty / serving_size_g
    - Recipe items via components: scaled by component.qty / ingredient.serving_size_g

    Any field that has no data for the period remains None.
    """
    user = await _get_or_create_user(db)

    # Validate range (cap at 366 days to avoid huge queries)
    if (end - start).days > 732:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 2 years")
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    totals: dict[str, float] = {}

    # ── 0. Snapshot macros from ALL items (ingredient AND recipe) ─────────────
    # Recipe items have ingredient_id=NULL (they use recipe_id) — they must still
    # count toward calories/protein/etc. via their snapshotted values.
    all_items_result = await db.execute(
        select(MealLogItem)
        .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
        )
    )
    for item in all_items_result.scalars().all():
        for field in _SNAPSHOT_FIELDS:
            val = getattr(item, field, None)
            if val is not None:
                _add_micro(totals, field, val)

    # ── 1. Direct ingredient items — micros only (macros handled above) ───────
    direct_result = await db.execute(
        select(MealLogItem, Ingredient)
        .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
        .join(Ingredient, MealLogItem.ingredient_id == Ingredient.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
            MealLogItem.ingredient_id.isnot(None),
        )
    )
    for item, ingredient in direct_result.all():
        # Use ingredient scaling for micros (vitamins, minerals, fiber, etc.)
        _accumulate_ingredient_micros(totals, ingredient, item.quantity_g)

    # ── 2. Recipe items via components ───────────────────────────────────────
    component_result = await db.execute(
        select(MealLogItemComponent, Ingredient)
        .join(MealLogItem, MealLogItemComponent.meal_log_item_id == MealLogItem.id)
        .join(MealLog,     MealLogItem.meal_log_id == MealLog.id)
        .join(Ingredient,  MealLogItemComponent.ingredient_id == Ingredient.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
            MealLogItemComponent.ingredient_id.isnot(None),
        )
    )
    for component, ingredient in component_result.all():
        _accumulate_ingredient_micros(totals, ingredient, component.quantity_g)

    # ── Days with at least one log entry ─────────────────────────────────────
    days_result = await db.execute(
        select(func.count(func.distinct(MealLog.log_date))).where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
        )
    )
    days_with_data = days_result.scalar() or 0

    # ── Build totals and per-day averages ─────────────────────────────────────
    totals_rounded = {k: round(v, 4) for k, v in totals.items()}

    daily_avg: dict[str, float] = {}
    if days_with_data > 0:
        daily_avg = {k: round(v / days_with_data, 4) for k, v in totals_rounded.items()}

    return MicronutrientSummaryRead(
        start_date=start,
        end_date=end,
        days_with_data=days_with_data,
        totals=MicronutrientTotals(**totals_rounded),
        daily_avg=MicronutrientTotals(**daily_avg),
    )


# ── GET /meals/nutrient-sources — foods contributing to one nutrient ────────

@router.get("/nutrient-sources")
async def get_nutrient_sources(
    nutrient: str = Query(..., description="Nutrient field name"),
    start: date_type = Query(..., description="Start date (yyyy-MM-dd)"),
    end:   date_type = Query(..., description="End date inclusive (yyyy-MM-dd)"),
    db:    AsyncSession = Depends(get_db),
):
    """Return the foods that contributed to one nutrient in a date range.

    Direct foods use their logged item. Recipe foods use their saved component
    snapshots, so the user can see the specific ingredient inside the recipe
    that supplied the nutrient.
    """
    valid_fields = _SNAPSHOT_FIELDS | set(_MICRO_FIELDS)
    if nutrient not in valid_fields:
        raise HTTPException(status_code=400, detail="Unknown nutrient")
    if (end - start).days > 732:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 2 years")
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    user = await _get_or_create_user(db)
    sources: dict[tuple[str, str | None], dict] = {}

    def add_source(name: str, detail: str | None, quantity_g: float, value: Optional[float]) -> None:
        if value is None or value == 0:
            return
        key = (name, detail)
        entry = sources.setdefault(key, {
            "name": name,
            "detail": detail,
            "quantity_g": 0.0,
            "value": 0.0,
        })
        entry["quantity_g"] += quantity_g or 0.0
        entry["value"] += value

    if nutrient in _SNAPSHOT_FIELDS:
        # These values are frozen on each diary item, including recipe entries.
        item_result = await db.execute(
            select(MealLogItem)
            .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
            .where(
                MealLog.user_id == user.id,
                MealLog.log_date >= start,
                MealLog.log_date <= end,
            )
        )
        for item in item_result.scalars().all():
            add_source(item.display_name, None, item.quantity_g, getattr(item, nutrient, None))
    else:
        # Direct foods contribute from their nutrient profile at the logged weight.
        direct_result = await db.execute(
            select(MealLogItem, Ingredient)
            .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
            .join(Ingredient, MealLogItem.ingredient_id == Ingredient.id)
            .where(
                MealLog.user_id == user.id,
                MealLog.log_date >= start,
                MealLog.log_date <= end,
                MealLogItem.ingredient_id.isnot(None),
            )
        )
        for item, ingredient in direct_result.all():
            raw = getattr(ingredient, nutrient, None)
            base_g = ingredient.serving_size_g or 100.0
            value = raw * (item.quantity_g / base_g) if raw is not None and base_g else None
            add_source(item.display_name, None, item.quantity_g, value)

        # Recipe ingredient snapshots retain the recipe context for clarity.
        component_result = await db.execute(
            select(MealLogItemComponent, MealLogItem, Ingredient)
            .join(MealLogItem, MealLogItemComponent.meal_log_item_id == MealLogItem.id)
            .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
            .join(Ingredient, MealLogItemComponent.ingredient_id == Ingredient.id)
            .where(
                MealLog.user_id == user.id,
                MealLog.log_date >= start,
                MealLog.log_date <= end,
                MealLogItemComponent.ingredient_id.isnot(None),
            )
        )
        for component, item, ingredient in component_result.all():
            raw = getattr(ingredient, nutrient, None)
            base_g = ingredient.serving_size_g or 100.0
            value = raw * (component.quantity_g / base_g) if raw is not None and base_g else None
            add_source(component.ingredient_name, item.display_name, component.quantity_g, value)

    days_result = await db.execute(
        select(func.count(func.distinct(MealLog.log_date))).where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
        )
    )
    days_with_data = days_result.scalar() or 0

    ordered = sorted(sources.values(), key=lambda entry: entry["value"], reverse=True)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days_with_data": days_with_data,
        "total": round(sum(entry["value"] for entry in ordered), 4),
        "sources": [
            {
                **entry,
                "quantity_g": round(entry["quantity_g"], 1),
                "value": round(entry["value"], 4),
            }
            for entry in ordered
        ],
    }


# ── GET /meals/daily-series — per-day macro totals for charting ───────────────

@router.get("/daily-series")
async def get_daily_series(
    start: date_type = Query(..., description="Start date (yyyy-MM-dd)"),
    end:   date_type = Query(..., description="End date inclusive (yyyy-MM-dd)"),
    db:    AsyncSession = Depends(get_db),
):
    """
    Return per-day totals of the core macros (from frozen snapshots, so recipe
    items are included). One row per calendar day that has at least one entry.
    Shape: [{ "date": "2026-07-01", "calories": 3200, "protein_g": 180, ... }]
    """
    user = await _get_or_create_user(db)
    if (end - start).days > 732:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 2 years")
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    result = await db.execute(
        select(
            MealLog.log_date,
            func.coalesce(func.sum(MealLogItem.calories), 0.0).label("calories"),
            func.coalesce(func.sum(MealLogItem.protein_g), 0.0).label("protein_g"),
            func.coalesce(func.sum(MealLogItem.carbs_g), 0.0).label("carbs_g"),
            func.coalesce(func.sum(MealLogItem.fat_g), 0.0).label("fat_g"),
            func.coalesce(func.sum(MealLogItem.sodium_mg), 0.0).label("sodium_mg"),
            func.coalesce(func.sum(MealLogItem.cholesterol_mg), 0.0).label("cholesterol_mg"),
        )
        .join(MealLogItem, MealLogItem.meal_log_id == MealLog.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
        )
        .group_by(MealLog.log_date)
        .order_by(MealLog.log_date)
    )
    return [
        {
            "date": row.log_date.isoformat(),
            "calories": round(row.calories, 1),
            "protein_g": round(row.protein_g, 1),
            "carbs_g": round(row.carbs_g, 1),
            "fat_g": round(row.fat_g, 1),
            "sodium_mg": round(row.sodium_mg, 1),
            "cholesterol_mg": round(row.cholesterol_mg, 1),
        }
        for row in result.all()
    ]


# ── GET /meals/nutrient-series — daily totals for any tracked nutrient ───────

@router.get("/nutrient-series")
async def get_nutrient_series(
    start: date_type = Query(..., description="Start date (yyyy-MM-dd)"),
    end:   date_type = Query(..., description="End date inclusive (yyyy-MM-dd)"),
    db:    AsyncSession = Depends(get_db),
):
    """
    Return per-day totals for every tracked macro and micronutrient. Unlike the
    lighter /daily-series endpoint, this includes vitamins, minerals, fatty
    acids, amino acids, and other nutrient details. Recipe micronutrients are
    calculated from their saved ingredient components.
    """
    user = await _get_or_create_user(db)
    if (end - start).days > 732:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 2 years")
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    daily: dict[date_type, dict[str, float]] = defaultdict(dict)

    def add(day: date_type, field: str, value: Optional[float]) -> None:
        if value is not None:
            daily[day][field] = round((daily[day].get(field) or 0.0) + value, 6)

    # Snapshot fields apply to every logged item, including recipe entries.
    items_result = await db.execute(
        select(MealLog.log_date, MealLogItem)
        .join(MealLogItem, MealLogItem.meal_log_id == MealLog.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
        )
    )
    for log_date, item in items_result.all():
        for field in _SNAPSHOT_FIELDS:
            add(log_date, field, getattr(item, field, None))

    # Direct food entries contribute their scaled nutrient profile.
    direct_result = await db.execute(
        select(MealLog.log_date, MealLogItem, Ingredient)
        .join(MealLogItem, MealLogItem.meal_log_id == MealLog.id)
        .join(Ingredient, MealLogItem.ingredient_id == Ingredient.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
            MealLogItem.ingredient_id.isnot(None),
        )
    )
    for log_date, item, ingredient in direct_result.all():
        base_g = ingredient.serving_size_g or 100.0
        ratio = item.quantity_g / base_g if base_g else 1.0
        for field in _MICRO_FIELDS:
            raw = getattr(ingredient, field, None)
            if raw is not None:
                add(log_date, field, raw * ratio)

    # Recipes use the ingredient-component snapshot created when they were logged.
    components_result = await db.execute(
        select(MealLog.log_date, MealLogItemComponent, Ingredient)
        .join(MealLogItem, MealLogItemComponent.meal_log_item_id == MealLogItem.id)
        .join(MealLog, MealLogItem.meal_log_id == MealLog.id)
        .join(Ingredient, MealLogItemComponent.ingredient_id == Ingredient.id)
        .where(
            MealLog.user_id == user.id,
            MealLog.log_date >= start,
            MealLog.log_date <= end,
            MealLogItemComponent.ingredient_id.isnot(None),
        )
    )
    for log_date, component, ingredient in components_result.all():
        base_g = ingredient.serving_size_g or 100.0
        ratio = component.quantity_g / base_g if base_g else 1.0
        for field in _MICRO_FIELDS:
            raw = getattr(ingredient, field, None)
            if raw is not None:
                add(log_date, field, raw * ratio)

    return [
        {"date": log_date.isoformat(), **{key: round(value, 4) for key, value in values.items()}}
        for log_date, values in sorted(daily.items())
    ]


# ── PATCH a meal log item ─────────────────────────────────────────────────────

@router.patch("/items/{item_id}", response_model=MealLogItemRead)
async def update_log_item(
    item_id: str,
    body:    MealLogItemUpdate,
    db:      AsyncSession = Depends(get_db),
):
    """Update quantity_g and/or logged_at for an existing log item. Macros are recalculated."""
    item = await db.get(MealLogItem, item_id, options=[selectinload(MealLogItem.components)])
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.quantity_g is not None and body.quantity_g != item.quantity_g:
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
            recipe_result = await db.execute(
                select(Recipe)
                .where(Recipe.id == item.recipe_id)
                .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
            )
            recipe = recipe_result.scalar_one_or_none()
            if recipe:
                macros = _scale_macros(recipe, body.quantity_g)
                old_qty = item.quantity_g
                item.quantity_g = body.quantity_g
                for k, v in macros.items():
                    setattr(item, k, v)

                # Re-scale components proportionally
                scale_factor = body.quantity_g / old_qty if old_qty else 1.0
                for comp in item.components:
                    comp.quantity_g = round(comp.quantity_g * scale_factor, 2)
            else:
                item.quantity_g = body.quantity_g

    if body.logged_at is not None:
        item.logged_at = body.logged_at

    # ── Move to a different meal number ───────────────────────────────────────
    old_meal_id = item.meal_log_id
    if body.meal_number is not None:
        old_meal = await db.get(MealLog, old_meal_id)
        if old_meal and body.meal_number != old_meal.meal_number:
            # Find or create the target MealLog for this date + new meal_number
            target_result = await db.execute(
                select(MealLog).where(
                    MealLog.user_id    == old_meal.user_id,
                    MealLog.log_date   == old_meal.log_date,
                    MealLog.meal_number == body.meal_number,
                )
            )
            target_meal = target_result.scalar_one_or_none()
            if not target_meal:
                target_meal = MealLog(
                    user_id=old_meal.user_id,
                    log_date=old_meal.log_date,
                    meal_number=body.meal_number,
                    logged_at=old_meal.logged_at,
                )
                db.add(target_meal)
                await db.flush()

            item.meal_log_id = target_meal.id
            await db.flush()

            # Recompute old meal totals
            old_remaining = await db.execute(
                select(MealLogItem).where(MealLogItem.meal_log_id == old_meal_id)
            )
            old_items = old_remaining.scalars().all()
            old_meal.total_calories       = round(sum(i.calories       for i in old_items), 2)
            old_meal.total_protein_g      = round(sum(i.protein_g      for i in old_items), 2)
            old_meal.total_fat_g          = round(sum(i.fat_g          for i in old_items), 2)
            old_meal.total_carbs_g        = round(sum(i.carbs_g        for i in old_items), 2)
            old_meal.total_sodium_mg      = round(sum(i.sodium_mg      for i in old_items), 2)
            old_meal.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in old_items), 2)
            await db.flush()

    await db.flush()

    # Recompute current meal totals
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


# ── PATCH / DELETE a logged recipe component ─────────────────────────────────

@router.patch("/items/{item_id}/components/{component_id}", response_model=MealLogItemRead)
async def update_logged_recipe_component(
    item_id: str,
    component_id: str,
    body: MealLogItemComponentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Change one ingredient for this logged recipe without editing the saved recipe."""
    item = await db.get(MealLogItem, item_id, options=[selectinload(MealLogItem.components)])
    if not item or not item.recipe_id:
        raise HTTPException(status_code=404, detail="Logged recipe not found")

    component = next((c for c in item.components if c.id == component_id), None)
    if not component:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    component.quantity_g = body.quantity_g
    await db.flush()
    await _recalculate_recipe_item_from_components(db, item)
    await db.flush()
    await _recalculate_meal_totals(db, item.meal_log_id)
    await db.flush()
    await db.refresh(item, attribute_names=["components"])
    return item


@router.delete("/items/{item_id}/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_logged_recipe_component(
    item_id: str,
    component_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Omit one ingredient from this day's recipe entry only."""
    item = await db.get(MealLogItem, item_id, options=[selectinload(MealLogItem.components)])
    if not item or not item.recipe_id:
        raise HTTPException(status_code=404, detail="Logged recipe not found")

    component = next((c for c in item.components if c.id == component_id), None)
    if not component:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    meal_id = item.meal_log_id
    await db.delete(component)
    await db.flush()

    remaining = await db.execute(
        select(MealLogItemComponent).where(MealLogItemComponent.meal_log_item_id == item.id)
    )
    if not remaining.scalars().first():
        # A recipe with no components is not a useful diary entry.
        await db.delete(item)
    else:
        await _recalculate_recipe_item_from_components(db, item)
    await db.flush()
    await _recalculate_meal_totals(db, meal_id)


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


# ── POST /meals/{meal_id}/copy ────────────────────────────────────────────────

@router.post("/{meal_id}/copy", response_model=MealLogRead, status_code=status.HTTP_201_CREATED)
async def copy_meal(meal_id: str, body: MealCopyRequest, db: AsyncSession = Depends(get_db)):
    """
    Copy all items from an existing meal to a new date / meal number.
    Components (recipe sub-ingredients) are copied alongside their parent items.
    """
    user = await _get_or_create_user(db)

    src_result = await db.execute(
        select(MealLog)
        .where(MealLog.id == meal_id, MealLog.user_id == user.id)
        .options(
            selectinload(MealLog.items)
            .selectinload(MealLogItem.components)
        )
    )
    source = src_result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Meal not found")
    if not source.items:
        raise HTTPException(status_code=400, detail="Meal has no items to copy")

    logged_at = body.logged_at or datetime.now(timezone.utc)

    tgt_result = await db.execute(
        select(MealLog).where(
            MealLog.user_id     == user.id,
            MealLog.log_date    == body.target_date,
            MealLog.meal_number == body.target_meal_number,
        ).options(
            selectinload(MealLog.items)
            .selectinload(MealLogItem.components)
        )
    )
    target = tgt_result.scalar_one_or_none()
    if not target:
        target = MealLog(
            user_id=user.id,
            log_date=body.target_date,
            meal_number=body.target_meal_number,
            logged_at=logged_at,
        )
        db.add(target)
        await db.flush()

    for src_item in source.items:
        new_item = MealLogItem(
            meal_log_id=target.id,
            ingredient_id=src_item.ingredient_id,
            recipe_id=src_item.recipe_id,
            display_name=src_item.display_name,
            quantity_g=src_item.quantity_g,
            logged_at=logged_at,
            calories=src_item.calories,
            protein_g=src_item.protein_g,
            fat_g=src_item.fat_g,
            carbs_g=src_item.carbs_g,
            sodium_mg=src_item.sodium_mg,
            cholesterol_mg=src_item.cholesterol_mg,
        )
        db.add(new_item)
        await db.flush()

        # Copy components
        for src_comp in src_item.components:
            db.add(MealLogItemComponent(
                meal_log_item_id=new_item.id,
                ingredient_id=src_comp.ingredient_id,
                ingredient_name=src_comp.ingredient_name,
                quantity_g=src_comp.quantity_g,
            ))

    await db.flush()

    all_items_result = await db.execute(select(MealLogItem).where(MealLogItem.meal_log_id == target.id))
    all_items = all_items_result.scalars().all()
    target.total_calories       = round(sum(i.calories       for i in all_items), 2)
    target.total_protein_g      = round(sum(i.protein_g      for i in all_items), 2)
    target.total_fat_g          = round(sum(i.fat_g          for i in all_items), 2)
    target.total_carbs_g        = round(sum(i.carbs_g        for i in all_items), 2)
    target.total_sodium_mg      = round(sum(i.sodium_mg      for i in all_items), 2)
    target.total_cholesterol_mg = round(sum(i.cholesterol_mg for i in all_items), 2)
    await db.flush()

    final = await db.execute(
        select(MealLog)
        .where(MealLog.id == target.id)
        .options(
            selectinload(MealLog.items)
            .selectinload(MealLogItem.components)
        )
    )
    return final.scalar_one()


# ── Daily Targets ─────────────────────────────────────────────────────────────

@router.post("/targets", response_model=DailyTargetRead, status_code=status.HTTP_201_CREATED)
async def set_daily_target(body: DailyTargetCreate, db: AsyncSession = Depends(get_db)):
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
    user = await _get_or_create_user(db)
    result = await db.execute(
        select(DailyTarget).where(DailyTarget.user_id == user.id)
        .order_by(desc(DailyTarget.target_date)).limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No targets set yet. POST /meals/targets first.")
    return row
