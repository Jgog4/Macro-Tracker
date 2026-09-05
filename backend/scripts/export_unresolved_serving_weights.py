"""Export personal foods that still need a verified gram conversion.

Usage:
    railway run python3 -m scripts.export_unresolved_serving_weights

The export is written beside the original Cronometer CSV by default.  It does
not modify the database.
"""
import asyncio
import csv
import os
import sys
from pathlib import Path

import asyncpg


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = BACKEND_DIR.parent / "Nutrition data" / "remaining_serving_weight_foods.csv"


def output_path() -> Path:
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            return Path(arg.split("=", 1)[1]).expanduser().resolve()
    return DEFAULT_OUTPUT


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required. Run with railway run.")

    conn = await asyncpg.connect(database_url)
    rows = await conn.fetch(
        """
        SELECT
            i.id,
            i.name,
            i.brand,
            i.serving_size_desc AS original_serving,
            i.calories,
            i.protein_g,
            i.carbs_g,
            i.fat_g,
            i.fiber_g,
            i.sodium_mg,
            COUNT(mli.id)::int AS diary_entries,
            MIN(ml.log_date) AS first_logged,
            MAX(ml.log_date) AS last_logged
        FROM mt_ingredients AS i
        LEFT JOIN mt_meal_log_items AS mli ON mli.ingredient_id = i.id
        LEFT JOIN mt_meal_logs AS ml ON ml.id = mli.meal_log_id
        WHERE i.source = 'personal'
          AND i.serving_size_g IS NULL
          AND i.serving_size_desc IS NOT NULL
        GROUP BY i.id
        ORDER BY diary_entries DESC, i.name
        """
    )
    await conn.close()

    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "food_id", "food_name", "brand", "original_serving", "calories_per_original_serving",
        "protein_g_per_original_serving", "carbs_g_per_original_serving",
        "fat_g_per_original_serving", "fiber_g_per_original_serving",
        "sodium_mg_per_original_serving", "diary_entries", "first_logged", "last_logged",
        "review_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            writer.writerow({
                "food_id": record["id"],
                "food_name": record["name"],
                "brand": record["brand"] or "",
                "original_serving": record["original_serving"],
                "calories_per_original_serving": record["calories"],
                "protein_g_per_original_serving": record["protein_g"],
                "carbs_g_per_original_serving": record["carbs_g"],
                "fat_g_per_original_serving": record["fat_g"],
                "fiber_g_per_original_serving": record["fiber_g"],
                "sodium_mg_per_original_serving": record["sodium_mg"],
                "diary_entries": record["diary_entries"],
                "first_logged": record["first_logged"] or "",
                "last_logged": record["last_logged"] or "",
                "review_status": "Needs verified grams per original serving",
            })
    print(f"Exported {len(rows)} foods to {path}")


if __name__ == "__main__":
    asyncio.run(main())
