"""
/export — download your data as CSV.

Plain CSV is deliberately chosen over a DB dump: it opens in Excel/Numbers,
is readable without any tooling, and stays useful long after this app is gone.
"""
import csv
import io
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.models import (
    Ingredient, MealLog, MealLogItem, Recipe, RecipeIngredient, DailyTarget, User,
)

router = APIRouter(prefix="/export", tags=["Export"])

DEFAULT_USER_EMAIL = "jesse@macro.app"


async def _user_id(db: AsyncSession) -> str | None:
    res = await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))
    u = res.scalar_one_or_none()
    return u.id if u else None


def _csv(rows: list[list], header: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _attach(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Builders (shared by the single-file and zip endpoints) ───────────────────

async def _food_log_csv(db: AsyncSession) -> str:
    uid = await _user_id(db)
    if not uid:
        return _csv([], ["date"])
    res = await db.execute(
        select(MealLog).where(MealLog.user_id == uid)
        .options(selectinload(MealLog.items))
        .order_by(MealLog.log_date, MealLog.meal_number)
    )
    rows = []
    for meal in res.scalars().all():
        for it in meal.items:
            rows.append([
                meal.log_date.isoformat(),
                meal.meal_number,
                (it.logged_at or meal.logged_at).isoformat() if (it.logged_at or meal.logged_at) else "",
                it.display_name,
                "recipe" if it.recipe_id else "food",
                round(it.quantity_g or 0, 2),
                round(it.calories or 0, 2),
                round(it.protein_g or 0, 2),
                round(it.carbs_g or 0, 2),
                round(it.fat_g or 0, 2),
                round(it.sodium_mg or 0, 2),
                round(it.cholesterol_mg or 0, 2),
            ])
    return _csv(rows, [
        "date", "meal_number", "logged_at_utc", "item", "type", "quantity_g",
        "calories", "protein_g", "carbs_g", "fat_g", "sodium_mg", "cholesterol_mg",
    ])


async def _daily_totals_csv(db: AsyncSession) -> str:
    uid = await _user_id(db)
    if not uid:
        return _csv([], ["date"])
    res = await db.execute(
        select(MealLog).where(MealLog.user_id == uid)
        .options(selectinload(MealLog.items)).order_by(MealLog.log_date)
    )
    days: dict = {}
    for meal in res.scalars().all():
        d = days.setdefault(meal.log_date, [0.0] * 6)
        for it in meal.items:
            d[0] += it.calories or 0
            d[1] += it.protein_g or 0
            d[2] += it.carbs_g or 0
            d[3] += it.fat_g or 0
            d[4] += it.sodium_mg or 0
            d[5] += it.cholesterol_mg or 0
    rows = [[d.isoformat()] + [round(v, 2) for v in vals] for d, vals in sorted(days.items())]
    return _csv(rows, ["date", "calories", "protein_g", "carbs_g", "fat_g", "sodium_mg", "cholesterol_mg"])


_FOOD_COLS = [
    "name", "brand", "source", "serving_size_g", "serving_size_desc",
    "calories", "protein_g", "carbs_g", "fat_g", "sat_fat_g", "trans_fat_g",
    "fiber_g", "sugar_g", "sodium_mg", "cholesterol_mg", "potassium_mg",
    "calcium_mg", "iron_mg", "magnesium_mg", "zinc_mg", "phosphorus_mg",
    "selenium_mcg", "iodine_mcg", "vitamin_a_mcg", "vitamin_c_mg", "vitamin_d_mcg",
    "vitamin_e_mg", "vitamin_k_mcg", "thiamine_mg", "riboflavin_mg", "niacin_mg",
    "folate_mcg", "cobalamin_mcg", "omega3_ala_g", "omega3_epa_g", "omega3_dha_g",
    "caffeine_mg", "alcohol_g",
]


async def _foods_csv(db: AsyncSession) -> str:
    res = await db.execute(select(Ingredient).order_by(Ingredient.name))
    rows = [[getattr(i, c, None) for c in _FOOD_COLS] for i in res.scalars().all()]
    return _csv(rows, _FOOD_COLS)


async def _recipes_csv(db: AsyncSession) -> str:
    res = await db.execute(select(Recipe).order_by(Recipe.name))
    rows = [[
        r.name, r.serving_size_g, r.total_weight_g, getattr(r, "num_servings", 1),
        r.calories, r.protein_g, r.carbs_g, r.fat_g, r.sodium_mg, r.cholesterol_mg,
    ] for r in res.scalars().all()]
    return _csv(rows, [
        "recipe", "serving_size_g", "total_weight_g", "num_servings",
        "calories", "protein_g", "carbs_g", "fat_g", "sodium_mg", "cholesterol_mg",
    ])


async def _recipe_ingredients_csv(db: AsyncSession) -> str:
    res = await db.execute(
        select(RecipeIngredient).options(
            selectinload(RecipeIngredient.recipe),
            selectinload(RecipeIngredient.ingredient),
        )
    )
    rows = []
    for ri in res.scalars().all():
        rows.append([
            ri.recipe.name if ri.recipe else "",
            ri.ingredient.name if ri.ingredient else "",
            ri.quantity_g,
        ])
    rows.sort(key=lambda r: (r[0], r[1]))
    return _csv(rows, ["recipe", "ingredient", "quantity_g"])


async def _targets_csv(db: AsyncSession) -> str:
    uid = await _user_id(db)
    if not uid:
        return _csv([], ["target_date"])
    res = await db.execute(
        select(DailyTarget).where(DailyTarget.user_id == uid).order_by(DailyTarget.target_date)
    )
    rows = [[t.target_date.isoformat(), t.calories, t.protein_g, t.carbs_g, t.fat_g,
             t.sodium_mg, t.cholesterol_mg] for t in res.scalars().all()]
    return _csv(rows, ["target_date", "calories", "protein_g", "carbs_g", "fat_g",
                       "sodium_mg", "cholesterol_mg"])


_EXPORTS = {
    "food_log":           ("food_log.csv",           _food_log_csv),
    "daily_totals":       ("daily_totals.csv",       _daily_totals_csv),
    "foods":              ("foods.csv",              _foods_csv),
    "recipes":            ("recipes.csv",            _recipes_csv),
    "recipe_ingredients": ("recipe_ingredients.csv", _recipe_ingredients_csv),
    "targets":            ("targets.csv",            _targets_csv),
}


@router.get("/{kind}.csv")
async def export_csv(kind: str, db: AsyncSession = Depends(get_db)):
    """Download one dataset as CSV."""
    if kind not in _EXPORTS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown export '{kind}'")
    filename, builder = _EXPORTS[kind]
    return _attach(await builder(db), filename)


@router.get("/all.zip")
async def export_all(db: AsyncSession = Depends(get_db)):
    """Download every dataset as a single ZIP — the full CSV backup."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for _, (filename, builder) in _EXPORTS.items():
            z.writestr(filename, await builder(db))
        z.writestr("README.txt",
                   "Macro Tracker CSV export\n"
                   f"Generated: {datetime.utcnow().isoformat()}Z\n\n"
                   "food_log.csv           one row per logged item\n"
                   "daily_totals.csv       one row per day\n"
                   "foods.csv              your food library\n"
                   "recipes.csv            recipe totals\n"
                   "recipe_ingredients.csv recipe components\n"
                   "targets.csv            macro targets\n")
    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="macro-tracker-export-{stamp}.zip"'},
    )
