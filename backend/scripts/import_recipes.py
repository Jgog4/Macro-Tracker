#!/usr/bin/env python3
"""
Import Cronometer recipe PDFs into Macro Tracker.

For each recipe PDF:
  1. Finds each ingredient in mt_ingredients by name (exact, then case-insensitive).
  2. Creates any ingredient not found as source='custom' with the calorie data
     extracted from the PDF.
  3. Creates an mt_recipes row with macro totals summed from ingredients.
  4. Creates mt_recipe_ingredients rows.
  5. Also creates an mt_ingredients proxy row (source='personal', recipe_id set)
     so the recipe can be searched and logged from the food library.

Usage (from /backend directory):
    railway run python3 -m scripts.import_recipes
"""

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
BACKEND_DIR   = SCRIPT_DIR.parent
NUTRITION_DIR = BACKEND_DIR.parent / "Nutrition Data"

# Load .env for local runs
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Run: railway run python3 -m scripts.import_recipes")
    sys.exit(1)
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed. Run: pip3 install asyncpg")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("❌ pdfplumber not installed. Run: pip3 install pdfplumber")
    sys.exit(1)

DEFAULT_USER_EMAIL = "jesse@macro.app"
CHUNK = 100


def _uid():
    return str(uuid.uuid4())


def _f(val):
    if val is None:
        return None
    try:
        v = float(str(val).strip())
        return v if v == v else None
    except (ValueError, AttributeError):
        return None


# ── PDF parsing ───────────────────────────────────────────────────────────────
def parse_recipe_pdf(path: Path):
    with pdfplumber.open(str(path)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # Recipe name: first line that isn't a URL/date
    name = ""
    for l in lines:
        if "cronometer.com" not in l and not re.match(r"^\d+/\d+/\d+", l):
            name = l
            break
    if not name:
        return None

    # Total recipe weight
    weight_match = re.search(r"Original Recipe Weight\s+([\d.]+)\s*g", full_text)
    total_weight = float(weight_match.group(1)) if weight_match else None

    # Per-100g nutrition from the Nutrition Facts panel (first occurrence)
    def first_num(pattern):
        m = re.search(pattern, full_text)
        return float(m.group(1)) if m else None

    # Grab individual label values (these are per-100g on Cronometer exports)
    cal_100   = first_num(r"Calories\s+([\d.]+)\s+kcal")
    prot_100  = first_num(r"Protein\s+([\d.]+)\s+g")
    carb_100  = first_num(r"Total Carbohydrate\s+([\d.]+)\s+g")
    fat_100   = first_num(r"Total Fat\s+([\d.]+)\s+g")
    fiber_100 = first_num(r"Dietary Fiber\s+([\d.]+)\s+g")
    sod_100   = first_num(r"Sodium\s+([\d.]+)\s+mg")
    chol_100  = first_num(r"Cholesterol\s+([\d.]+)\s+mg")
    sat_100   = first_num(r"Saturated Fat\s+([\d.]+)\s+g")
    sug_100   = first_num(r"Sugars\s+([\d.]+)\s+g")

    # Ingredients table: lines matching "Name  DB  amount  unit  kcal  weight g"
    ingredients = []
    ing_section = re.search(
        r"Ingredients\s*\n(.*?)(?:\n\d+\s*g\s*\n|General Amount|$)",
        full_text, re.DOTALL
    )
    if ing_section:
        for line in ing_section.group(1).strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("Description") or line.startswith("Amount"):
                continue
            m = re.match(
                r"^(.+?)\s+(?:CRDB|NCCDB|USDA|CUSTOM|\w+DB)\s+([\d.]+)\s+\w+\s+([\d.]+)\s+([\d.]+)\s*g\s*$",
                line
            )
            if m:
                ingredients.append({
                    "name":     m.group(1).strip(),
                    "weight_g": float(m.group(4)),
                    "calories": float(m.group(3)),
                })

    return {
        "name":         name,
        "total_weight_g": total_weight,
        "ingredients":  ingredients,
        "per_100g": {
            "calories":      cal_100,
            "protein_g":     prot_100,
            "carbs_g":       carb_100,
            "fat_g":         fat_100,
            "fiber_g":       fiber_100,
            "sodium_mg":     sod_100,
            "cholesterol_mg":chol_100,
            "sat_fat_g":     sat_100,
            "sugar_g":       sug_100,
        },
    }


def load_all_recipes() -> list[dict]:
    pdfs = sorted(NUTRITION_DIR.glob("*.pdf"))
    recipes = []
    for pdf in pdfs:
        r = parse_recipe_pdf(pdf)
        if r and r["ingredients"]:
            recipes.append(r)
        elif r:
            print(f"  ⚠️  {r['name']}: no ingredients parsed — skipping")
    return recipes


# ── DB helpers ────────────────────────────────────────────────────────────────
async def get_user_id(conn) -> str:
    row = await conn.fetchrow("SELECT id FROM mt_users WHERE email=$1", DEFAULT_USER_EMAIL)
    if row:
        return row["id"]
    uid = _uid()
    await conn.execute(
        "INSERT INTO mt_users (id, email, name) VALUES ($1,$2,$3)",
        uid, DEFAULT_USER_EMAIL, "Jesse"
    )
    return uid


async def build_name_index(conn) -> dict[str, str]:
    """Return {lower(name): id} for every row in mt_ingredients."""
    rows = await conn.fetch("SELECT id, name FROM mt_ingredients")
    return {r["name"].lower(): r["id"] for r in rows}


async def find_or_create_ingredient(conn, ing_name: str, weight_g: float,
                                    calories: float, name_index: dict) -> str:
    """
    Return ingredient id. Creates a minimal 'custom' ingredient if not found.
    Updates name_index in-place.
    """
    key = ing_name.lower()
    if key in name_index:
        return name_index[key]

    # Try partial match (first 40 chars)
    for k, v in name_index.items():
        if k.startswith(key[:40]) or key.startswith(k[:40]):
            return v

    # Not found — create a stub ingredient
    ing_id = _uid()
    # Estimate per-100g from the given weight and calories
    cal_per_100 = round(calories / weight_g * 100, 2) if weight_g else 0.0
    await conn.execute("""
        INSERT INTO mt_ingredients
          (id, source, name, serving_size_g, serving_size_desc,
           calories, protein_g, fat_g, carbs_g,
           created_at, updated_at)
        VALUES ($1,'custom',$2,$3,$4,$5,0,0,0,NOW(),NOW())
    """, ing_id, ing_name, weight_g, f"{int(weight_g)} g", cal_per_100)
    name_index[key] = ing_id
    return ing_id


async def compute_recipe_totals(conn, recipe_ings: list[dict]) -> dict:
    """
    Sum macros across all recipe ingredients using scaled ingredient data.
    Falls back to just calories if ingredient macros are missing.
    """
    totals = dict(calories=0.0, protein_g=0.0, fat_g=0.0, carbs_g=0.0,
                  sodium_mg=0.0, cholesterol_mg=0.0)
    for ri in recipe_ings:
        row = await conn.fetchrow(
            "SELECT serving_size_g, calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg "
            "FROM mt_ingredients WHERE id=$1", ri["ingredient_id"]
        )
        if not row:
            continue
        base_g = row["serving_size_g"] or ri["quantity_g"]
        ratio  = ri["quantity_g"] / base_g if base_g else 1.0
        totals["calories"]      += (row["calories"]      or 0) * ratio
        totals["protein_g"]     += (row["protein_g"]     or 0) * ratio
        totals["fat_g"]         += (row["fat_g"]         or 0) * ratio
        totals["carbs_g"]       += (row["carbs_g"]       or 0) * ratio
        totals["sodium_mg"]     += (row["sodium_mg"]     or 0) * ratio
        totals["cholesterol_mg"]+= (row["cholesterol_mg"]or 0) * ratio
    return {k: round(v, 2) for k, v in totals.items()}


# ── Main import ───────────────────────────────────────────────────────────────
async def main():
    print("📂 Scanning recipe PDFs…")
    recipes = load_all_recipes()
    print(f"   → {len(recipes)} recipes with ingredients found")

    print("🔌 Connecting to database…")
    conn = await asyncpg.connect(
        DATABASE_URL,
        server_settings={"tcp_keepalives_idle": "60"},
        command_timeout=120,
    )

    try:
        user_id = await get_user_id(conn)
        print(f"   ✓ User: {DEFAULT_USER_EMAIL}")

        print("📚 Building ingredient name index…")
        name_index = await build_name_index(conn)
        print(f"   → {len(name_index)} existing ingredients indexed")

        # Delete any existing recipes with the same names (clean re-run)
        recipe_names = [r["name"] for r in recipes]
        await conn.execute(
            "DELETE FROM mt_recipes WHERE name = ANY($1::text[])", recipe_names
        )

        imported = 0
        skipped  = 0

        for recipe in recipes:
            if not recipe["ingredients"]:
                skipped += 1
                continue

            print(f"\n🍽️  {recipe['name']}  ({len(recipe['ingredients'])} ingredients, {recipe['total_weight_g']}g)")

            # ── Resolve / create ingredients ──────────────────────────────────
            recipe_ing_rows = []
            for ing in recipe["ingredients"]:
                ing_id = await find_or_create_ingredient(
                    conn, ing["name"], ing["weight_g"], ing["calories"], name_index
                )
                recipe_ing_rows.append({
                    "ingredient_id": ing_id,
                    "quantity_g":    ing["weight_g"],
                    "name":          ing["name"],
                })
                print(f"   ✓  {ing['name'][:45]:45s}  {ing['weight_g']:6.1f}g")

            # ── Create recipe ─────────────────────────────────────────────────
            recipe_id = _uid()
            totals    = await compute_recipe_totals(conn, recipe_ing_rows)

            await conn.execute("""
                INSERT INTO mt_recipes
                  (id, name, total_weight_g, serving_size_g,
                   calories, protein_g, fat_g, carbs_g,
                   sodium_mg, cholesterol_mg,
                   created_at, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW(),NOW())
            """,
                recipe_id,
                recipe["name"],
                recipe["total_weight_g"],
                recipe["total_weight_g"],   # default: 1 serving = full recipe
                totals["calories"],
                totals["protein_g"],
                totals["fat_g"],
                totals["carbs_g"],
                totals["sodium_mg"],
                totals["cholesterol_mg"],
            )

            # ── Create recipe ingredients ─────────────────────────────────────
            ri_rows = [
                (_uid(), recipe_id, ri["ingredient_id"], ri["quantity_g"])
                for ri in recipe_ing_rows
            ]
            await conn.executemany("""
                INSERT INTO mt_recipe_ingredients (id, recipe_id, ingredient_id, quantity_g)
                VALUES ($1,$2,$3,$4)
            """, ri_rows)

            # ── Create proxy ingredient so recipe appears in Library search ───
            proxy_id = _uid()
            await conn.execute("""
                INSERT INTO mt_ingredients
                  (id, source, name, serving_size_g, serving_size_desc,
                   recipe_id,
                   calories, protein_g, fat_g, carbs_g,
                   sodium_mg, cholesterol_mg,
                   created_at, updated_at)
                VALUES ($1,'personal',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),NOW())
                ON CONFLICT DO NOTHING
            """,
                proxy_id,
                recipe["name"],
                recipe["total_weight_g"],
                f"{int(recipe['total_weight_g'] or 0)} g (full recipe)",
                recipe_id,
                totals["calories"],
                totals["protein_g"],
                totals["fat_g"],
                totals["carbs_g"],
                totals["sodium_mg"],
                totals["cholesterol_mg"],
            )

            print(f"   → {totals['calories']:.0f} kcal | {totals['protein_g']:.1f}g P | "
                  f"{totals['carbs_g']:.1f}g C | {totals['fat_g']:.1f}g F")
            imported += 1

    finally:
        await conn.close()

    print(f"\n🎉 Done — {imported} recipes imported, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())
