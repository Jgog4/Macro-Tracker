"""Find and repair Cronometer-imported foods whose serving weight is missing.

The original Cronometer CSV stores nutrition for the logged serving.  When that
serving was expressed as a piece, cup, or other non-gram unit, the original
importer did not know its gram weight and used 100 g as a placeholder.  This
script resolves only *high-confidence* generic USDA matches by comparing the
macro pattern independent of serving size.  It never replaces the original
nutrition; it only records the inferred gram weight and updates matching
historical placeholder quantities.

Usage:
    railway run python3 -m scripts.audit_serving_weights --limit=25
    railway run python3 -m scripts.audit_serving_weights --limit=25 --apply

Run the review mode first.  Branded and restaurant foods are deliberately left
for label-specific verification, even if their names resemble a USDA result.
"""
import asyncio
import os
import re
import sys
from typing import Optional, Tuple

import asyncpg
import httpx


MACRO_IDS = {1008: "calories", 1003: "protein_g", 1004: "fat_g", 1005: "carbs_g"}
STOP_WORDS = {
    "and", "or", "with", "without", "raw", "fresh", "cooked", "dry", "the",
    "of", "in", "from", "food", "foods", "organic", "frozen", "unsweetened",
}


def option(name: str, default: int) -> int:
    prefix = f"{name}="
    for arg in sys.argv[1:]:
        if arg.startswith(prefix):
            return max(1, int(arg[len(prefix):]))
    return default


def tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {
        word[:-1] if word.endswith("s") and len(word) > 4 else word
        for word in words if word not in STOP_WORDS
    }


def macros(food: dict) -> dict[str, float]:
    values: dict[str, float] = {}
    for nutrient in food.get("foodNutrients", []):
        nutrient_id = nutrient.get("nutrientId") or nutrient.get("nutrient", {}).get("id")
        field = MACRO_IDS.get(nutrient_id)
        value = nutrient.get("value")
        if value is None:
            value = nutrient.get("amount")
        if field and value is not None and field not in values:
            values[field] = float(value)
    return values


def profile_error(source: asyncpg.Record, candidate: dict[str, float]) -> Optional[Tuple[float, float]]:
    """Return (mean macro error, inferred grams) using calories as the scale."""
    source_calories = float(source["calories"] or 0)
    candidate_calories = candidate.get("calories", 0)
    if source_calories < 10 or candidate_calories < 10:
        return None
    grams = source_calories / candidate_calories * 100.0
    if not 0.5 <= grams <= 2500:
        return None

    errors = []
    for field in ("protein_g", "carbs_g", "fat_g"):
        actual = float(source[field] or 0)
        expected = candidate.get(field)
        if expected is None or max(actual, expected * grams / 100.0) < 1.0:
            continue
        predicted = expected * grams / 100.0
        errors.append(abs(actual - predicted) / max(actual, predicted, 1.0))
    return (sum(errors) / len(errors), grams) if errors else None


async def usda_search(client: httpx.AsyncClient, query: str, api_key: str) -> list[dict]:
    response = await client.post(
        "https://api.nal.usda.gov/fdc/v1/foods/search",
        params={"api_key": api_key},
        json={"query": query, "pageSize": 20, "dataType": ["Foundation", "SR Legacy"]},
    )
    response.raise_for_status()
    return response.json().get("foods", [])


async def main() -> None:
    if not os.environ.get("USDA_API_KEY"):
        raise RuntimeError("USDA_API_KEY is required")
    apply = "--apply" in sys.argv
    limit = option("--limit", 25)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    rows = await conn.fetch(
        """
        SELECT * FROM mt_ingredients
        WHERE source = 'personal'
          AND serving_size_g IS NULL
          AND serving_size_desc IS NOT NULL
          AND calories >= 10
        ORDER BY (
            SELECT COUNT(*) FROM mt_meal_log_items AS history
            WHERE history.ingredient_id = mt_ingredients.id
        ) DESC, name
        LIMIT $1
        """,
        limit,
    )

    approved: list[tuple[asyncpg.Record, dict, float, float]] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for row in rows:
            query = re.sub(r"[,()]", " ", row["name"])
            try:
                candidates = await usda_search(client, query, os.environ["USDA_API_KEY"])
            except httpx.HTTPError as exc:
                print(f"ERROR  {row['name']}: USDA search failed ({exc})")
                continue

            source_tokens = tokens(row["name"])
            scored = []
            for candidate in candidates:
                candidate_macros = macros(candidate)
                profile = profile_error(row, candidate_macros)
                if not profile:
                    continue
                error, grams = profile
                candidate_tokens = tokens(candidate.get("description", ""))
                coverage = len(source_tokens & candidate_tokens) / max(len(source_tokens), 1)
                scored.append((coverage, error, grams, candidate))

            safe = [entry for entry in scored if entry[0] >= 0.67 and entry[1] <= 0.08]
            if not safe:
                print(f"SKIP    {row['name']} | {row['serving_size_desc']}")
                continue
            coverage, error, grams, candidate = sorted(safe, key=lambda x: (-x[0], x[1]))[0]
            print(
                f"MATCH   {row['name']} | {row['serving_size_desc']}\n"
                f"        -> {candidate['fdcId']} {candidate.get('description')} | "
                f"{grams:.1f} g, name={coverage:.0%}, macro error={error:.1%}"
            )
            approved.append((row, candidate, grams, error))

    if apply:
        async with conn.transaction():
            for row, candidate, grams, _ in approved:
                desc = f"{row['serving_size_desc']} ({grams:.1f} g)"
                await conn.execute(
                    "UPDATE mt_ingredients SET serving_size_g = $1, serving_size_desc = $2 "
                    "WHERE id = $3",
                    grams, desc, row["id"],
                )
                await conn.execute(
                    "UPDATE mt_meal_log_items SET quantity_g = $1 "
                    "WHERE ingredient_id = $2 AND quantity_g = 100",
                    grams, row["id"],
                )
        print(f"\nApplied {len(approved)} high-confidence conversions.")
    else:
        print(f"\n{len(approved)} high-confidence conversions found. Nothing was changed.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
