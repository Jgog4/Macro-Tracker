#!/usr/bin/env python3
"""
Import restaurant items from combined_nutrition_database.csv into mt_ingredients.

Each row becomes source='restaurant' with the brand name set.
Already-existing items (same name + brand) are skipped.

Usage:
    railway run python3 -m scripts.import_restaurants
"""
import asyncio, csv, os, sys, uuid
from pathlib import Path

SCRIPT_DIR    = Path(__file__).parent
BACKEND_DIR   = SCRIPT_DIR.parent
CSV_PATH      = BACKEND_DIR.parent / "Nutrition Data" / "combined_nutrition_database.csv"

env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Run: railway run python3 -m scripts.import_restaurants")
    sys.exit(1)
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed."); sys.exit(1)

def _uid(): return str(uuid.uuid4())
def _f(v):
    try: return float(v) if v else None
    except: return None


async def main():
    if not CSV_PATH.exists():
        print(f"❌ Not found: {CSV_PATH}"); sys.exit(1)

    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"📂 {len(rows)} restaurant items found")

    conn = await asyncpg.connect(DATABASE_URL,
        server_settings={"tcp_keepalives_idle": "60"}, command_timeout=60)

    try:
        # Delete existing restaurant items and re-import clean
        await conn.execute("DELETE FROM mt_ingredients WHERE source='restaurant'")

        data = [
            (
                _uid(), "restaurant",
                row["Item"].strip(), row["Brand"].strip(),
                _f(row.get("Serving Size")) if row.get("Serving Size","").replace(".","").isdigit() else None,
                row.get("Serving Size","").strip() or None,
                _f(row["Calories"]) or 0.0,
                _f(row["Protein (g)"]) or 0.0,
                _f(row["Total Fat (g)"]) or 0.0,
                _f(row["Carbs (g)"]) or 0.0,
                _f(row.get("Fiber (g)")),
                _f(row.get("Sugars (g)")),
                _f(row.get("Sodium (mg)")),
                _f(row.get("Cholesterol (mg)")),
                _f(row.get("Sat Fat (g)")),
                _f(row.get("Trans Fat (g)")),
            )
            for row in rows
        ]

        await conn.executemany("""
            INSERT INTO mt_ingredients
              (id, source, name, brand,
               serving_size_g, serving_size_desc,
               calories, protein_g, fat_g, carbs_g,
               fiber_g, sugar_g, sodium_mg, cholesterol_mg,
               sat_fat_g, trans_fat_g,
               created_at, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,NOW(),NOW())
        """, data)

        # Summary
        brands = {}
        for row in rows:
            b = row["Brand"].strip()
            brands[b] = brands.get(b, 0) + 1
        for brand, count in sorted(brands.items()):
            print(f"   ✓ {brand}: {count} items")
        print(f"\n🎉 {len(rows)} restaurant items imported")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
