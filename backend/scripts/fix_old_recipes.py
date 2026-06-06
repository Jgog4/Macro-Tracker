#!/usr/bin/env python3
"""
Fix Turkey & rice and Bison and rice recipes whose ingredients
couldn't be parsed automatically (multi-line names in PDF).

Clears existing recipe_ingredients for each recipe and re-inserts
the correct ones, then recalculates macro totals.

Usage:
    railway run python3 -m scripts.fix_old_recipes
"""
import asyncio, os, sys, uuid
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent

env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Run: railway run python3 -m scripts.fix_old_recipes")
    sys.exit(1)
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed."); sys.exit(1)

def _uid(): return str(uuid.uuid4())

# ── Hardcoded ingredient lists from the PDFs ──────────────────────────────────
RECIPES = [
    {
        "name": "Turkey & rice",
        "total_weight_g": 516.0,
        "ingredients": [
            {"name": "Rice, White, Long-Grain, Regular, Enriched, Cooked", "weight_g": 270.0},
            {"name": "Aroy-d, Red Curry Paste",                            "weight_g":  30.0},
            {"name": "Ground turkey, Fat Free, Raw",                       "weight_g": 176.0},
            {"name": "Chili oil (lemon grass)",                            "weight_g":  20.0},
            {"name": "Carrots, Raw",                                       "weight_g":  40.0},
        ],
    },
    {
        "name": "Bison and rice",
        "total_weight_g": 495.0,
        "ingredients": [
            {"name": "Rangeland Bison, Ground Bison, Extra-Lean", "weight_g": 225.0},
            {"name": "Rice, White, Long-Grain, Regular, Enriched, Cooked", "weight_g": 250.0},
            {"name": "Chili oil (lemon grass)",                           "weight_g":  20.0},
            {"name": "Aroy-D, Red Curry Paste",                           "weight_g":  30.0},
        ],
    },
]


async def find_ingredient(conn, name: str):
    """Exact match first, then case-insensitive."""
    row = await conn.fetchrow(
        "SELECT id, serving_size_g, calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg "
        "FROM mt_ingredients WHERE name = $1", name
    )
    if row:
        return row
    row = await conn.fetchrow(
        "SELECT id, serving_size_g, calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg "
        "FROM mt_ingredients WHERE lower(name) = lower($1)", name
    )
    return row


async def create_stub(conn, name: str, weight_g: float):
    """Create a minimal ingredient stub so the recipe link works."""
    ing_id = _uid()
    await conn.execute("""
        INSERT INTO mt_ingredients
          (id, source, name, serving_size_g, serving_size_desc,
           calories, protein_g, fat_g, carbs_g, created_at, updated_at)
        VALUES ($1,'custom',$2,$3,$4, 0,0,0,0, NOW(),NOW())
    """, ing_id, name, weight_g, f"{int(weight_g)} g")
    print(f"     ⚠️  Created stub for '{name}' (no match found in library)")
    return ing_id


async def scale_macro(row, field, weight_g):
    base_g = row["serving_size_g"] or weight_g
    ratio  = weight_g / base_g if base_g else 1.0
    return round((row[field] or 0) * ratio, 2)


async def main():
    conn = await asyncpg.connect(
        DATABASE_URL,
        server_settings={"tcp_keepalives_idle": "60"},
        command_timeout=60,
    )

    try:
        for recipe_def in RECIPES:
            name = recipe_def["name"]
            print(f"\n🍽️  {name}")

            recipe_row = await conn.fetchrow(
                "SELECT id FROM mt_recipes WHERE lower(name) = lower($1)", name
            )
            if not recipe_row:
                # Create a fresh recipe row
                recipe_id = _uid()
                await conn.execute("""
                    INSERT INTO mt_recipes (id, name, total_weight_g, serving_size_g,
                        calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg,
                        created_at, updated_at)
                    VALUES ($1,$2,$3,$3, 0,0,0,0,0,0, NOW(),NOW())
                """, recipe_id, name, recipe_def["total_weight_g"])
                print(f"   Created new recipe row")
            else:
                recipe_id = recipe_row["id"]
                # Clear old recipe_ingredients
                await conn.execute("DELETE FROM mt_recipe_ingredients WHERE recipe_id=$1", recipe_id)
                print(f"   Cleared existing recipe_ingredients")

            # Resolve ingredients and build new links
            ri_rows   = []
            cal_total = prot_total = fat_total = carb_total = sod_total = chol_total = 0.0

            for ing_def in recipe_def["ingredients"]:
                ing_name  = ing_def["name"]
                weight_g  = ing_def["weight_g"]

                ing_row = await find_ingredient(conn, ing_name)
                if ing_row:
                    ing_id = ing_row["id"]
                    print(f"   ✓  {ing_name[:50]:50s}  {weight_g:5.0f}g  (matched)")
                    cal_total  += await scale_macro(ing_row, "calories",      weight_g)
                    prot_total += await scale_macro(ing_row, "protein_g",     weight_g)
                    fat_total  += await scale_macro(ing_row, "fat_g",         weight_g)
                    carb_total += await scale_macro(ing_row, "carbs_g",       weight_g)
                    sod_total  += await scale_macro(ing_row, "sodium_mg",     weight_g)
                    chol_total += await scale_macro(ing_row, "cholesterol_mg",weight_g)
                else:
                    ing_id = await create_stub(conn, ing_name, weight_g)

                ri_rows.append((_uid(), recipe_id, ing_id, weight_g))

            await conn.executemany("""
                INSERT INTO mt_recipe_ingredients (id, recipe_id, ingredient_id, quantity_g)
                VALUES ($1,$2,$3,$4)
            """, ri_rows)

            # Update recipe totals
            await conn.execute("""
                UPDATE mt_recipes SET
                    total_weight_g=$1, serving_size_g=$1,
                    calories=$2, protein_g=$3, fat_g=$4, carbs_g=$5,
                    sodium_mg=$6, cholesterol_mg=$7, updated_at=NOW()
                WHERE id=$8
            """, recipe_def["total_weight_g"],
                round(cal_total, 2), round(prot_total, 2), round(fat_total, 2),
                round(carb_total, 2), round(sod_total, 2), round(chol_total, 2),
                recipe_id)

            # Also update the proxy ingredient if it exists
            await conn.execute("""
                UPDATE mt_ingredients SET
                    calories=$1, protein_g=$2, fat_g=$3, carbs_g=$4,
                    sodium_mg=$5, cholesterol_mg=$6, updated_at=NOW()
                WHERE recipe_id=$7
            """, round(cal_total, 2), round(prot_total, 2), round(fat_total, 2),
                round(carb_total, 2), round(sod_total, 2), round(chol_total, 2),
                recipe_id)

            print(f"   → {cal_total:.0f} kcal | {prot_total:.1f}g P | "
                  f"{carb_total:.1f}g C | {fat_total:.1f}g F")
            print(f"   ✅ {len(ri_rows)} ingredients linked")

    finally:
        await conn.close()

    print("\n🎉 Done")


if __name__ == "__main__":
    asyncio.run(main())
