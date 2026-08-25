"""Review likely USDA matches for frequently logged foods missing priority micros.

This is intentionally audit-only. It never changes the database.  It compares
the app's per-100 g macro profile with USDA Foundation/SR Legacy search results
and prints only high-confidence generic-food candidates for human review.

Examples:
    railway run python3 -m scripts.audit_micronutrient_matches
    railway run python3 -m scripts.audit_micronutrient_matches --limit=20

Run in small batches: the free USDA key is rate-limited and branded products
need a label-specific source rather than a generic USDA substitution.
"""
import asyncio
import os
import re
import sys
from collections import Counter

import asyncpg
import httpx


PRIORITY_FIELDS = (
    "choline_mg", "iodine_mcg", "biotin_mcg", "chromium_mcg", "molybdenum_mcg",
)
MACRO_IDS = {1008: "calories", 1003: "protein_g", 1004: "fat_g", 1005: "carbs_g"}
STOP_WORDS = {
    "raw", "fresh", "cooked", "dry", "with", "without", "and", "or", "the",
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
    # Singularisation is deliberately minimal; this is only a candidate audit.
    return {word[:-1] if word.endswith("s") and len(word) > 4 else word
            for word in words if word not in STOP_WORDS}


def nutrient_amounts(food: dict) -> dict[str, float]:
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


def macro_error(app: dict, candidate: dict) -> float:
    """Mean relative error, weighting calories more heavily than tiny macros."""
    errors = []
    for field in ("calories", "protein_g", "carbs_g", "fat_g"):
        expected, actual = app[field], candidate.get(field)
        if actual is None:
            return 999.0
        # Sub-1 g nutrients are too noisy to judge a food match.
        if max(expected, actual) < 1.0:
            continue
        errors.append(abs(expected - actual) / max(expected, actual, 1.0))
    return sum(errors) / len(errors) if errors else 999.0


async def usda_search(client: httpx.AsyncClient, query: str, api_key: str) -> list[dict]:
    response = await client.post(
        "https://api.nal.usda.gov/fdc/v1/foods/search",
        params={"api_key": api_key},
        json={"query": query, "pageSize": 12, "dataType": ["Foundation", "SR Legacy"]},
    )
    response.raise_for_status()
    return response.json().get("foods", [])


async def main() -> None:
    if not os.environ.get("USDA_API_KEY"):
        raise RuntimeError("USDA_API_KEY is required")
    limit = option("--limit", 15)
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    priority_sql = " OR ".join(f"i.{field} IS NULL" for field in PRIORITY_FIELDS)
    rows = await conn.fetch(f"""
        SELECT i.*, COUNT(*)::int AS uses
        FROM mt_ingredients i
        JOIN (
            SELECT ingredient_id FROM mt_meal_log_items WHERE ingredient_id IS NOT NULL
            UNION ALL
            SELECT ingredient_id FROM mt_meal_log_item_components WHERE ingredient_id IS NOT NULL
        ) history ON history.ingredient_id = i.id
        WHERE i.usda_fdc_id IS NULL
          AND i.brand IS NULL
          AND i.source IN ('personal', 'custom')
          AND ({priority_sql})
        GROUP BY i.id
        ORDER BY uses DESC, i.name
        LIMIT $1
    """, limit)
    await conn.close()

    print(f"Reviewing {len(rows)} high-use generic foods (no writes)\n")
    approved = 0
    async with httpx.AsyncClient(timeout=20.0) as client:
        for row in rows:
            base_g = row["serving_size_g"] or 100.0
            app_macros = {
                field: (row[field] or 0.0) * 100.0 / base_g
                for field in ("calories", "protein_g", "carbs_g", "fat_g")
            }
            try:
                candidates = await usda_search(client, row["name"], os.environ["USDA_API_KEY"])
            except httpx.HTTPError as exc:
                print(f"ERROR  {row['name']}: USDA search failed ({exc})")
                continue

            app_tokens = tokens(row["name"])
            scored = []
            for candidate in candidates:
                candidate_tokens = tokens(candidate.get("description", ""))
                overlap = len(app_tokens & candidate_tokens) / max(len(app_tokens | candidate_tokens), 1)
                nutrients = nutrient_amounts(candidate)
                error = macro_error(app_macros, nutrients)
                scored.append((overlap, error, candidate, nutrients))

            # Require a near-identical generic name and close calories/macros.
            safe = [entry for entry in scored if entry[0] >= 0.70 and entry[1] <= 0.15]
            if safe:
                overlap, error, candidate, nutrients = sorted(safe, key=lambda x: (-x[0], x[1]))[0]
                missing = ", ".join(field for field in PRIORITY_FIELDS if row[field] is None)
                print(
                    f"REVIEW  uses={row['uses']:>3}  {row['name']}\n"
                    f"        → FDC {candidate['fdcId']}: {candidate.get('description')}\n"
                    f"        name={overlap:.0%} macro difference={error:.0%}; missing {missing}"
                )
                approved += 1
            else:
                print(f"SKIP    uses={row['uses']:>3}  {row['name']} (no safe generic USDA match)")

    print(f"\n{approved} candidates for manual review. Nothing was changed.")


if __name__ == "__main__":
    asyncio.run(main())
