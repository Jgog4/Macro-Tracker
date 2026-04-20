#!/usr/bin/env python3
"""
One-time fix: personal food macros were seeded as per-100g values but
serving_size_g was set to the user's typical serving (e.g. 10g for honey).

This meant _scale_macros divided qty / serving_size_g instead of qty / 100,
returning ~10x too many calories.

Fix: multiply every stored macro by (serving_size_g / 100) so values match
what the user actually eats at that serving size.

Usage (from /backend directory):
    railway run python3 -m scripts.fix_personal_macros
"""
import asyncio
import os
import sys
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
    print("❌ DATABASE_URL not set.")
    sys.exit(1)

DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

import asyncpg


async def main():
    print("🌱 Connecting…")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.execute("""
            UPDATE mt_ingredients
            SET
                calories       = ROUND((calories       * serving_size_g / 100)::numeric, 4),
                protein_g      = ROUND((protein_g      * serving_size_g / 100)::numeric, 4),
                fat_g          = ROUND((fat_g          * serving_size_g / 100)::numeric, 4),
                carbs_g        = ROUND((carbs_g        * serving_size_g / 100)::numeric, 4),
                fiber_g        = CASE WHEN fiber_g       IS NOT NULL
                                 THEN ROUND((fiber_g       * serving_size_g / 100)::numeric, 4) END,
                sugar_g        = CASE WHEN sugar_g        IS NOT NULL
                                 THEN ROUND((sugar_g        * serving_size_g / 100)::numeric, 4) END,
                sodium_mg      = CASE WHEN sodium_mg      IS NOT NULL
                                 THEN ROUND((sodium_mg      * serving_size_g / 100)::numeric, 4) END,
                cholesterol_mg = CASE WHEN cholesterol_mg IS NOT NULL
                                 THEN ROUND((cholesterol_mg * serving_size_g / 100)::numeric, 4) END,
                sat_fat_g      = CASE WHEN sat_fat_g      IS NOT NULL
                                 THEN ROUND((sat_fat_g      * serving_size_g / 100)::numeric, 4) END,
                trans_fat_g    = CASE WHEN trans_fat_g    IS NOT NULL
                                 THEN ROUND((trans_fat_g    * serving_size_g / 100)::numeric, 4) END
            WHERE source = 'personal'
              AND serving_size_g IS NOT NULL
              AND serving_size_g != 100
        """)
        print(f"✅ Fixed: {result}")
        # Spot-check honey
        row = await conn.fetchrow(
            "SELECT name, serving_size_g, calories FROM mt_ingredients "
            "WHERE source='personal' AND name ILIKE '%honey%' LIMIT 1"
        )
        if row:
            print(f"   Spot-check — {row['name']}: {row['serving_size_g']}g → {row['calories']} kcal ✓")
    finally:
        await conn.close()
    print("🎉 Done")


if __name__ == "__main__":
    asyncio.run(main())
