"""
/suggest — "What should I eat?" decision engine.

Algorithm:
1. Pull today's DailySummaryRead (consumed so far).
2. Compute remaining fat_g and protein_g budget.
3. Query restaurant ingredients for items whose macros are closest
   to the remaining budget without significantly overshooting.
4. Rank by fit_score = 1 - normalised_distance.
5. Return top 3.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Ingredient, MealLog
from app.routers.meals import _get_or_create_user
from app.schemas.schemas import SuggestionRead, IngredientRead

router = APIRouter(prefix="/suggest", tags=["Decision Engine"])


@router.get("/", response_model=list[SuggestionRead])
async def suggest_foods(
    log_date: date = Query(default_factory=date.today),
    top_n:    int  = Query(3, ge=1, le=10),
    db:       AsyncSession = Depends(get_db),
):
    """
    Returns the top-N restaurant/custom meals that best fit the remaining
    fat & protein budget for the given day.

    Fit score methodology
    ─────────────────────
    • Compute remaining_protein = target_protein - consumed_protein
    • Compute remaining_fat     = target_fat     - consumed_fat
    • For each candidate ingredient:
        delta_protein = remaining_protein - ingredient.protein_g
        delta_fat     = remaining_fat     - ingredient.fat_g
        distance      = sqrt(delta_protein² + delta_fat²)   [Euclidean]
    • fit_score = 1 / (1 + distance)   → higher is closer
    • Only include candidates that don't OVERSHOOT both macros.
    """
    from app.models.models import DailyTarget
    from sqlalchemy import desc

    user = await _get_or_create_user(db)

    # ── Fetch targets ────────────────────────────────────────────────────────
    tgt_result = await db.execute(
        select(DailyTarget)
        .where(DailyTarget.user_id == user.id, DailyTarget.target_date <= log_date)
        .order_by(desc(DailyTarget.target_date)).limit(1)
    )
    target = tgt_result.scalar_one_or_none()
    target_protein = target.protein_g if target else 244.3
    target_fat     = target.fat_g     if target else 90.5

    # ── Compute consumed today ───────────────────────────────────────────────
    meals_result = await db.execute(
        select(MealLog).where(MealLog.user_id == user.id, MealLog.log_date == log_date)
    )
    meals = meals_result.scalars().all()
    consumed_protein = sum(m.total_protein_g for m in meals)
    consumed_fat     = sum(m.total_fat_g     for m in meals)

    remaining_protein = max(0.0, target_protein - consumed_protein)
    remaining_fat     = max(0.0, target_fat     - consumed_fat)

    # ── Fetch candidate ingredients (restaurant + custom) ────────────────────
    candidates_result = await db.execute(
        select(Ingredient).where(
            Ingredient.source.in_(["restaurant", "custom"]),
            Ingredient.protein_g.isnot(None),
            Ingredient.fat_g.isnot(None),
        ).limit(500)
    )
    candidates = candidates_result.scalars().all()

    # ── Score ─────────────────────────────────────────────────────────────────
    import math

    scored = []
    for ing in candidates:
        dp = remaining_protein - (ing.protein_g or 0)
        df = remaining_fat     - (ing.fat_g     or 0)

        # Penalise heavily if the item overshoots BOTH macros
        if dp < -5 and df < -5:
            continue

        distance  = math.sqrt(dp**2 + df**2)
        fit_score = round(1 / (1 + distance), 4)

        scored.append(SuggestionRead(
            ingredient=IngredientRead.model_validate(ing),
            fit_score=fit_score,
            delta_protein_g=round(dp, 1),
            delta_fat_g=round(df, 1),
        ))

    scored.sort(key=lambda s: s.fit_score, reverse=True)
    return scored[:top_n]
