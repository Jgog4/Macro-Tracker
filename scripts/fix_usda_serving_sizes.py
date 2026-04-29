#!/usr/bin/env python3
"""
fix_usda_serving_sizes.py
─────────────────────────
Re-fetches USDA foods that are missing serving_size_g and updates them in-place.

Run from the project root:
  DATABASE_URL=<your-railway-url> python scripts/fix_usda_serving_sizes.py

Or just let the expanded unit logic in usda.py handle new imports going forward —
this script is only needed to backfill existing rows.
"""
import asyncio
import os
import sys
import httpx

# ── minimal async DB setup without importing the full FastAPI app ─────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: set DATABASE_URL env var to your Railway PostgreSQL URL")
    sys.exit(1)

USDA_API_KEY  = os.environ.get("USDA_API_KEY", "DEMO_KEY")
USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

GRAM_UNITS = {"g", "grm", "gram", "grams", "gr"}
OZ_UNITS   = {"oz", "ounce", "ounces"}
ML_UNITS   = {"ml", "milliliter", "milliliters", "millilitre"}


def unit_to_grams(size, unit: str):
    u = unit.lower().strip()
    if u in GRAM_UNITS: return float(size)
    if u in OZ_UNITS:   return round(float(size) * 28.3495, 1)
    if u in ML_UNITS:   return float(size)
    return None


async def main():
    # Use asyncpg directly
    try:
        import asyncpg
    except ImportError:
        print("Installing asyncpg…")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "asyncpg", "--break-system-packages", "-q"])
        import asyncpg

    # Railway URL uses postgres:// — asyncpg needs postgresql://
    db_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")

    conn = await asyncpg.connect(db_url)

    # Find USDA foods with no serving_size_g but with an FDC id
    rows = await conn.fetch(
        "SELECT id, name, usda_fdc_id FROM ingredients "
        "WHERE source = 'usda' AND usda_fdc_id IS NOT NULL AND serving_size_g IS NULL "
        "LIMIT 500"
    )
    print(f"Found {len(rows)} USDA foods missing serving_size_g")

    updated = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for row in rows:
            fdc_id = row["usda_fdc_id"]
            try:
                resp = await client.get(
                    f"{USDA_BASE_URL}/food/{fdc_id}",
                    params={"api_key": USDA_API_KEY},
                )
                if resp.status_code != 200:
                    continue
                food = resp.json()
                size = food.get("servingSize")
                unit = food.get("servingSizeUnit", "")
                if size and unit:
                    grams = unit_to_grams(size, unit)
                    if grams:
                        desc = f"{size} {unit}"
                        await conn.execute(
                            "UPDATE ingredients SET serving_size_g=$1, serving_size_desc=$2 WHERE id=$3",
                            grams, desc, row["id"]
                        )
                        print(f"  ✓ {row['name'][:50]:<50}  {desc} → {grams}g")
                        updated += 1
            except Exception as e:
                print(f"  ✗ {row['name'][:50]}: {e}")

    await conn.close()
    print(f"\nDone — updated {updated}/{len(rows)} foods")


if __name__ == "__main__":
    asyncio.run(main())
