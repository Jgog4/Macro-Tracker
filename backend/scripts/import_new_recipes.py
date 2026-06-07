#!/usr/bin/env python3
"""
Import 10 new recipes from AI Data > Macro Tracker App > Nutrition Data > New Recipes.
Ingredients manually extracted from PDFs (multi-line names can't be auto-parsed).

Usage:
    railway run python3 -m scripts.import_new_recipes
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
    print("❌ DATABASE_URL not set. Run: railway run python3 -m scripts.import_new_recipes")
    sys.exit(1)
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed."); sys.exit(1)

def _uid(): return str(uuid.uuid4())

# ── All 10 recipes ────────────────────────────────────────────────────────────
RECIPES = [
    {
        "name": "Baja taco sauce",
        "total_weight_g": 52.0,
        "ingredients": [
            {"name": "Olympic, Organic Sour Cream",                  "weight_g": 30.0},
            {"name": "Lime Juice, Raw",                              "weight_g": 44.0},
            {"name": "Casa Fiesta, Chipotle Peppers in Adobo Sauce", "weight_g": 42.0},
            {"name": "Salt",                                         "weight_g":  2.0},
            {"name": "Garlic, Fresh",                                "weight_g":  6.0},
        ],
    },
    {
        "name": "Breakfast berry smoothie",
        "total_weight_g": 350.0,
        "ingredients": [
            {"name": "Raspberries, Frozen, Unsweetened",                        "weight_g": 140.0},
            {"name": "Dates, Medjool",                                          "weight_g":  48.0},
            {"name": "Almond Breeze, Unsweetened, Original",                    "weight_g": 240.0},
            {"name": "Walnuts",                                                 "weight_g":  25.0},
            {"name": "Kirkland Signature, Roasted Whole Cashews, Unsalted",     "weight_g":  25.0},
            {"name": "Whey Protein Powder, 24 Grams of Protein per Scoop",     "weight_g":  31.0},
            {"name": "Bananas, Raw",                                            "weight_g":  81.0},
        ],
    },
    {
        "name": "Cavatelli",
        "total_weight_g": 1232.0,
        "ingredients": [
            {"name": "Semolina Flour", "weight_g": 620.0},
            {"name": "Tap Water",      "weight_g": 612.0},
        ],
    },
    {
        "name": "Dutch baby",
        "total_weight_g": 386.0,
        "ingredients": [
            {"name": "Butter, Salted",                "weight_g":  28.4},
            {"name": "White All-Purpose Flour, Enriched", "weight_g": 62.5},
            {"name": "Milk, Whole",                   "weight_g": 122.0},
            {"name": "Sugars, Granulated",            "weight_g":   4.2},
            {"name": "Nutmeg",                        "weight_g":   1.0},
            {"name": "Eggs, Cooked (golden )",        "weight_g": 168.0},
        ],
    },
    {
        "name": "Fish curry base (no fish)",
        "total_weight_g": 867.8,
        "ingredients": [
            {"name": "Cock Brand, Cooking Tamarind, Concentrate",        "weight_g":  45.0},
            {"name": "Thai Agri Foods, Savoy, Coconut Cream",            "weight_g": 198.4},
            {"name": "Tomato, Canned",                                   "weight_g": 398.0},
            {"name": "Kirkland Signature, Organic Virgin Coconut Oil",   "weight_g":  35.0},
            {"name": "Garam Masala",                                     "weight_g":  10.0},
            {"name": "Onion, White, Yellow or Red, Raw",                 "weight_g": 150.0},
            {"name": "Jalapeño Peppers, Raw",                            "weight_g":  45.0},
            {"name": "Ginger Root, Raw",                                 "weight_g":  10.0},
            {"name": "Garlic, Fresh",                                    "weight_g":  12.0},
            {"name": "Turmeric, Ground",                                 "weight_g":   9.4},
        ],
    },
    {
        "name": "Lamb kofta",
        "total_weight_g": 1115.0,
        "ingredients": [
            {"name": "Onion, White, Yellow or Red, Raw",              "weight_g": 210.0},
            {"name": "New Zealand Spring Lamb, Lean Ground Lamb",     "weight_g": 500.0},
            {"name": "Kirkland Signature, Organic Lean Ground Beef",  "weight_g": 250.0},
            {"name": "Red Bell Peppers, Raw",                         "weight_g": 130.0},
            {"name": "Parsley, Fresh",                                "weight_g":  25.0},
        ],
    },
    {
        "name": "Peanut oat smoothie",
        "total_weight_g": 220.0,
        "ingredients": [
            {"name": "One Degree Organic Foods, Gluten Free Sprouted Rolled Oats, Canada", "weight_g":  80.0},
            {"name": "PB2, Organic Powdered Peanut Butter",                                "weight_g":  15.0},
            {"name": "Ghost, Whey Protein, Peanut Butter Cereal Milk",                    "weight_g":  60.0},
            {"name": "Maple Syrup",                                                        "weight_g":  40.0},
            {"name": "Peanut Butter, Natural, Unsalted",                                   "weight_g":  25.0},
            {"name": "Kirkland Signature, Almond Beverage, Vanilla",                       "weight_g": 240.0},
        ],
    },
    {
        "name": "Piri piri sauce",
        "total_weight_g": 721.0,
        "ingredients": [
            {"name": "Olive Oil",                            "weight_g":  54.0},
            {"name": "Red Bell Peppers, Raw",                "weight_g": 164.0},
            {"name": "Onion, White, Yellow or Red, Raw",     "weight_g":  55.0},
            {"name": "Honey",                                "weight_g":  42.4},
            {"name": "Hot Chili Peppers, Red, Raw",          "weight_g":  75.0},
            {"name": "Salt",                                 "weight_g":  18.2},
            {"name": "Lemon Juice, Raw",                     "weight_g": 120.0},
            {"name": "Orange Juice, Fresh",                  "weight_g": 173.6},
            {"name": "Paprika Seasoning",                    "weight_g":   6.8},
            {"name": "Garlic, Fresh",                        "weight_g":  12.0},
        ],
    },
    {
        "name": "Rendang beef",
        "total_weight_g": 1139.0,
        "ingredients": [
            {"name": "Everland, Organic Shredded Coconut, Unsweetened",  "weight_g":  49.0},
            {"name": "Kirkland Signature, Organic Virgin Coconut Oil",   "weight_g":  48.0},
            {"name": "Eastland, Palm Sugar",                             "weight_g":  62.0},
            {"name": "Ribs, Beef, Short, No Visible Fat Eaten",          "weight_g": 550.0},
            {"name": "Swad, Tamarind Paste",                             "weight_g":  30.0},
            {"name": "Thai Agri Foods, Savoy, Coconut Cream",            "weight_g": 400.0},
        ],
    },
    {
        "name": "Tinga de pollo",
        "total_weight_g": 570.0,
        "ingredients": [
            {"name": "Olive Oil",                                        "weight_g":  10.0},
            {"name": "Onion, White, Yellow or Red, Raw",                 "weight_g": 105.0},
            {"name": "San Marcos, Chipotle Peppers In Adobo Sauce",      "weight_g":  60.0},
            {"name": "Italissima, Fire Roasted Diced Tomatoes",          "weight_g": 270.0},
            {"name": "Chicken Breast, Skinless, Cooked",                 "weight_g": 395.0},
        ],
    },
]


# ── DB helpers (same pattern as fix_old_recipes.py) ───────────────────────────
async def find_ingredient(conn, name):
    row = await conn.fetchrow(
        "SELECT id, serving_size_g, calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg "
        "FROM mt_ingredients WHERE name = $1", name
    )
    if row: return row
    return await conn.fetchrow(
        "SELECT id, serving_size_g, calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg "
        "FROM mt_ingredients WHERE lower(name) = lower($1)", name
    )


async def create_stub(conn, name, weight_g):
    ing_id = _uid()
    await conn.execute("""
        INSERT INTO mt_ingredients
          (id, source, name, serving_size_g, serving_size_desc,
           calories, protein_g, fat_g, carbs_g, created_at, updated_at)
        VALUES ($1,'custom',$2,$3,$4, 0,0,0,0, NOW(),NOW())
    """, ing_id, name, weight_g, f"{int(weight_g)} g")
    print(f"     ⚠️  Created stub: '{name}'")
    return ing_id


async def scale(row, field, weight_g):
    base = row["serving_size_g"] or weight_g
    ratio = weight_g / base if base else 1.0
    return round((row[field] or 0) * ratio, 2)


async def main():
    conn = await asyncpg.connect(DATABASE_URL,
        server_settings={"tcp_keepalives_idle": "60"}, command_timeout=120)

    try:
        names = [r["name"] for r in RECIPES]
        await conn.execute("DELETE FROM mt_recipes WHERE name = ANY($1::text[])", names)

        for recipe_def in RECIPES:
            name = recipe_def["name"]
            print(f"\n🍽️  {name}  ({len(recipe_def['ingredients'])} ingredients)")

            recipe_id = _uid()
            await conn.execute("""
                INSERT INTO mt_recipes (id, name, total_weight_g, serving_size_g,
                    calories, protein_g, fat_g, carbs_g, sodium_mg, cholesterol_mg,
                    created_at, updated_at)
                VALUES ($1,$2,$3,$3, 0,0,0,0,0,0, NOW(),NOW())
            """, recipe_id, name, recipe_def["total_weight_g"])

            ri_rows = []
            cal = prot = fat = carb = sod = chol = 0.0

            for ing_def in recipe_def["ingredients"]:
                ing_row = await find_ingredient(conn, ing_def["name"])
                if ing_row:
                    ing_id = ing_row["id"]
                    status = "matched"
                    cal  += await scale(ing_row, "calories",       ing_def["weight_g"])
                    prot += await scale(ing_row, "protein_g",      ing_def["weight_g"])
                    fat  += await scale(ing_row, "fat_g",          ing_def["weight_g"])
                    carb += await scale(ing_row, "carbs_g",        ing_def["weight_g"])
                    sod  += await scale(ing_row, "sodium_mg",      ing_def["weight_g"])
                    chol += await scale(ing_row, "cholesterol_mg", ing_def["weight_g"])
                else:
                    ing_id = await create_stub(conn, ing_def["name"], ing_def["weight_g"])
                    status = "stub"
                print(f"   {'✓' if status=='matched' else '⚠'}  {ing_def['name'][:50]:50s}  {ing_def['weight_g']:6.1f}g")
                ri_rows.append((_uid(), recipe_id, ing_id, ing_def["weight_g"]))

            await conn.executemany("""
                INSERT INTO mt_recipe_ingredients (id, recipe_id, ingredient_id, quantity_g)
                VALUES ($1,$2,$3,$4)
            """, ri_rows)

            await conn.execute("""
                UPDATE mt_recipes SET
                    calories=$1, protein_g=$2, fat_g=$3, carbs_g=$4,
                    sodium_mg=$5, cholesterol_mg=$6, updated_at=NOW()
                WHERE id=$7
            """, round(cal,2), round(prot,2), round(fat,2), round(carb,2),
                round(sod,2), round(chol,2), recipe_id)

            # Proxy ingredient for food search
            await conn.execute("""
                INSERT INTO mt_ingredients
                  (id, source, name, serving_size_g, serving_size_desc,
                   recipe_id, calories, protein_g, fat_g, carbs_g,
                   sodium_mg, cholesterol_mg, created_at, updated_at)
                VALUES ($1,'personal',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW(),NOW())
                ON CONFLICT DO NOTHING
            """, _uid(), name, recipe_def["total_weight_g"],
                f"{int(recipe_def['total_weight_g'])} g (full recipe)",
                recipe_id,
                round(cal,2), round(prot,2), round(fat,2), round(carb,2),
                round(sod,2), round(chol,2))

            print(f"   → {cal:.0f} kcal | {prot:.1f}g P | {carb:.1f}g C | {fat:.1f}g F")

    finally:
        await conn.close()

    print(f"\n🎉 {len(RECIPES)} recipes imported")


if __name__ == "__main__":
    asyncio.run(main())
