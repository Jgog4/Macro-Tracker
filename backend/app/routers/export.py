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
    Ingredient, MealLog, MealLogItem, MealLogItemComponent,
    Recipe, RecipeIngredient, DailyTarget, User,
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



# Every nutrient beyond the core macros, grouped for a readable CSV.
_MICRO_COLS = [
    # fats
    "sat_fat_g", "trans_fat_g", "monounsaturated_fat_g", "polyunsaturated_fat_g",
    "omega3_ala_g", "omega3_epa_g", "omega3_dha_g", "omega6_la_g", "omega6_aa_g",
    "phytosterol_mg", "cholesterol_mg",
    # carbs detail
    "fiber_g", "soluble_fiber_g", "insoluble_fiber_g", "sugar_g", "added_sugar_g",
    "fructose_g", "galactose_g", "glucose_g", "lactose_g", "maltose_g", "sucrose_g",
    # minerals
    "sodium_mg", "potassium_mg", "calcium_mg", "iron_mg", "magnesium_mg",
    "phosphorus_mg", "zinc_mg", "copper_mg", "manganese_mg", "selenium_mcg",
    "chromium_mcg", "iodine_mcg", "molybdenum_mcg", "fluoride_mg",
    # vitamins
    "vitamin_a_mcg", "retinol_mcg", "beta_carotene_mcg", "alpha_carotene_mcg",
    "beta_cryptoxanthin_mcg", "lutein_zeaxanthin_mcg", "lycopene_mcg",
    "vitamin_c_mg", "vitamin_d_mcg", "vitamin_e_mg", "beta_tocopherol_mg",
    "gamma_tocopherol_mg", "delta_tocopherol_mg", "vitamin_k_mcg",
    "thiamine_mg", "riboflavin_mg", "niacin_mg", "pantothenic_acid_mg",
    "pyridoxine_mg", "cobalamin_mcg", "biotin_mcg", "folate_mcg", "choline_mg",
    # amino acids
    "alanine_g", "arginine_g", "aspartic_acid_g", "cystine_g", "glutamic_acid_g",
    "glycine_g", "histidine_g", "hydroxyproline_g", "isoleucine_g", "leucine_g",
    "lysine_g", "methionine_g", "phenylalanine_g", "proline_g", "serine_g",
    "threonine_g", "tryptophan_g", "tyrosine_g", "valine_g",
    # other
    "caffeine_mg", "alcohol_g", "water_g", "ash_g", "oxalate_mg", "phytate_mg",
    "beta_hydroxybutyrate_g",
]


def _scale(ing, qty_g: float) -> dict:
    """
    Micros for `qty_g` of an ingredient.

    NOTE: micronutrients are NOT snapshotted on the log item (only the 6 core
    macros are), so they're recomputed from the ingredient's current values —
    exactly what the Reports page does.
    """
    base = (ing.serving_size_g or 100.0) if ing else 100.0
    r = (qty_g or 0) / base if base else 0.0
    return {c: (getattr(ing, c, None) or 0.0) * r for c in _MICRO_COLS}


async def _micro_context(db: AsyncSession):
    """Pre-load ingredients + recipe-component snapshots so the export is one pass."""
    ing_res = await db.execute(select(Ingredient))
    ings = {i.id: i for i in ing_res.scalars().all()}

    comp_res = await db.execute(select(MealLogItemComponent))
    comps: dict = {}
    for c in comp_res.scalars().all():
        comps.setdefault(c.meal_log_item_id, []).append(c)
    return ings, comps


def _item_micros(item, ings: dict, comps: dict) -> dict:
    """Micros for one logged item — direct ingredient, or summed recipe components."""
    if item.ingredient_id and item.ingredient_id in ings:
        return _scale(ings[item.ingredient_id], item.quantity_g)

    totals = {c: 0.0 for c in _MICRO_COLS}
    for comp in comps.get(item.id, []):
        ing = ings.get(comp.ingredient_id)
        if not ing:
            continue
        for k, v in _scale(ing, comp.quantity_g).items():
            totals[k] += v
    return totals


# ── Builders (shared by the single-file and zip endpoints) ───────────────────

async def _food_log_csv(db: AsyncSession) -> str:
    uid = await _user_id(db)
    if not uid:
        return _csv([], ["date"])
    ings, comps = await _micro_context(db)
    res = await db.execute(
        select(MealLog).where(MealLog.user_id == uid)
        .options(selectinload(MealLog.items))
        .order_by(MealLog.log_date, MealLog.meal_number)
    )
    rows = []
    for meal in res.scalars().all():
        for it in meal.items:
            micros = _item_micros(it, ings, comps)
            # sodium & cholesterol are snapshotted at log time — trust those
            micros["sodium_mg"]      = it.sodium_mg      or 0.0
            micros["cholesterol_mg"] = it.cholesterol_mg or 0.0
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
            ] + [round(micros.get(c, 0.0), 4) for c in _MICRO_COLS])
    header = [
        "date", "meal_number", "logged_at_utc", "item", "type", "quantity_g",
        "calories", "protein_g", "carbs_g", "fat_g",
    ] + _MICRO_COLS
    return _csv(rows, header)


async def _daily_totals_csv(db: AsyncSession) -> str:
    """One row per day: core macros (from frozen snapshots) + every micronutrient."""
    uid = await _user_id(db)
    if not uid:
        return _csv([], ["date"])
    ings, comps = await _micro_context(db)
    res = await db.execute(
        select(MealLog).where(MealLog.user_id == uid)
        .options(selectinload(MealLog.items)).order_by(MealLog.log_date)
    )
    days: dict = {}
    for meal in res.scalars().all():
        d = days.setdefault(meal.log_date, {"calories": 0.0, "protein_g": 0.0,
                                            "carbs_g": 0.0, "fat_g": 0.0,
                                            **{c: 0.0 for c in _MICRO_COLS}})
        for it in meal.items:
            d["calories"]  += it.calories  or 0
            d["protein_g"] += it.protein_g or 0
            d["carbs_g"]   += it.carbs_g   or 0
            d["fat_g"]     += it.fat_g     or 0
            m = _item_micros(it, ings, comps)
            m["sodium_mg"]      = it.sodium_mg      or 0.0
            m["cholesterol_mg"] = it.cholesterol_mg or 0.0
            for k, v in m.items():
                d[k] += v
    cols = ["calories", "protein_g", "carbs_g", "fat_g"] + _MICRO_COLS
    rows = [[day.isoformat()] + [round(vals[c], 4) for c in cols]
            for day, vals in sorted(days.items())]
    return _csv(rows, ["date"] + cols)


_FOOD_COLS = [
    "name", "brand", "source", "serving_size_g", "serving_size_desc",
    "calories", "protein_g", "carbs_g", "fat_g",
] + _MICRO_COLS


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
                   "food_log.csv           one row per logged item (macros + micronutrients)\n"
                   "daily_totals.csv       one row per day (macros + micronutrients)\n"
                   "foods.csv              your food library\n"
                   "recipes.csv            recipe totals\n"
                   "recipe_ingredients.csv recipe components\n"
                   "targets.csv            macro targets\n\n"
                   "Core macros (calories/protein/carbs/fat/sodium/cholesterol) are the\n"
                   "values frozen at log time. Micronutrients are not snapshotted, so they\n"
                   "are recomputed from each food's current nutrition data - the same basis\n"
                   "the in-app Reports page uses.\n")
    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="macro-tracker-export-{stamp}.zip"'},
    )
