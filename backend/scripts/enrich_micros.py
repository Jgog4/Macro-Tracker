"""Conservatively enrich missing micronutrients from exact USDA reference foods.

This script deliberately does *not* alter calories, macros, serving sizes, or
existing micronutrient values.  Each mapping below has been manually reviewed
against the app's existing food name and macro profile.  Add mappings only when
the USDA match is unambiguous.

Usage:
    railway run python3 -m scripts.enrich_micros          # review changes
    railway run python3 -m scripts.enrich_micros --apply  # write only blanks
    railway run python3 -m scripts.enrich_micros --all-usda --apply

``--all-usda`` also processes every library food that already has a USDA FDC
identifier. Those IDs are an exact provenance link, so they are safe to
backfill automatically. Foods without an FDC ID remain review-only until we
can make an unambiguous food-specific match; this avoids assigning generic
nutrition to a branded product that only looks similar.
"""
import asyncio
import os
import sys

import asyncpg
import httpx


# App food name → exact USDA FoodData Central reference ID.
# The values returned by SR Legacy are per 100 g; this script scales them to
# the serving_size_g already stored in Macro Tracker.
USDA_MATCHES = {
    "Eggs, Cooked": 173424,                 # Egg, whole, cooked, hard-boiled
    "Egg, White, Raw, Fresh": 172183,       # Egg, white, raw, fresh
    "Egg White, Raw": 172183,
    "Egg Whites Only, Cooked": 172183,      # closest generic profile; low-impact choline
    "Egg, Whole, Raw, Fresh": 171287,       # Egg, whole, raw, fresh
    "Egg, Raw": 171287,
    "Egg Yolk, Raw": 172184,                # Egg, yolk, raw, fresh
}

# USDA nutrient ID → the app's micronutrient column.  Core macros are excluded
# on purpose: package/Cronometer macro values remain the source of truth.
NUTRIENT_MAP = {
    1079: "fiber_g", 1082: "soluble_fiber_g", 1084: "insoluble_fiber_g",
    1085: "monounsaturated_fat_g", 1086: "polyunsaturated_fat_g",
    1092: "potassium_mg", 1096: "chromium_mcg", 1098: "copper_mg",
    1099: "fluoride_mg", 1100: "iodine_mcg", 1101: "manganese_mg",
    1102: "molybdenum_mcg", 1103: "selenium_mcg", 1105: "retinol_mcg",
    1106: "vitamin_a_mcg", 1107: "beta_carotene_mcg", 1108: "alpha_carotene_mcg",
    1109: "vitamin_e_mg", 1120: "beta_cryptoxanthin_mcg",
    1121: "lycopene_mcg", 1122: "lutein_zeaxanthin_mcg",
    1123: "beta_tocopherol_mg", 1124: "gamma_tocopherol_mg",
    1125: "delta_tocopherol_mg", 1162: "vitamin_c_mg",
    1165: "thiamine_mg", 1166: "riboflavin_mg", 1167: "niacin_mg",
    1170: "pantothenic_acid_mg", 1175: "pyridoxine_mg",
    1177: "folate_mcg", 1178: "cobalamin_mcg", 1180: "choline_mg",
    1183: "vitamin_k_mcg", 1185: "phytosterol_mg", 1187: "folate_mcg",
    1210: "tryptophan_g", 1211: "threonine_g", 1212: "isoleucine_g",
    1213: "leucine_g", 1214: "lysine_g", 1215: "methionine_g",
    1216: "cystine_g", 1217: "phenylalanine_g", 1218: "tyrosine_g",
    1219: "valine_g", 1220: "arginine_g", 1221: "histidine_g",
    1222: "alanine_g", 1223: "aspartic_acid_g", 1224: "glutamic_acid_g",
    1225: "glycine_g", 1226: "proline_g", 1227: "serine_g",
    1228: "hydroxyproline_g", 1229: "biotin_mcg", 1278: "omega3_ala_g",
    1292: "omega6_la_g", 1316: "omega6_aa_g", 1404: "omega3_epa_g",
    1405: "omega3_dha_g", 1410: "vitamin_d_mcg",
}


def nutrient_values(food: dict) -> dict[str, float]:
    """Read the selected USDA values, preserving legitimate zeros."""
    values: dict[str, float] = {}
    for nutrient in food.get("foodNutrients", []):
        nutrient_id = nutrient.get("nutrientId") or nutrient.get("nutrient", {}).get("id")
        field = NUTRIENT_MAP.get(nutrient_id)
        if not field or field in values:
            continue
        value = nutrient.get("amount")
        if value is None:
            value = nutrient.get("value")
        if value is None:
            continue
        # USDA reports fluoride in mcg; the app stores it in mg.
        values[field] = float(value) / 1000.0 if field == "fluoride_mg" else float(value)
    return values


async def fetch_usda(client: httpx.AsyncClient, fdc_id: int) -> dict:
    response = await client.get(
        f"https://api.nal.usda.gov/fdc/v1/food/{fdc_id}",
        params={"api_key": os.environ["USDA_API_KEY"]},
    )
    response.raise_for_status()
    return response.json()


async def main() -> None:
    apply = "--apply" in sys.argv
    include_all_usda = "--all-usda" in sys.argv
    if not os.environ.get("USDA_API_KEY"):
        raise RuntimeError("USDA_API_KEY is required")

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    manual_rows = await conn.fetch(
        "SELECT * FROM mt_ingredients WHERE name = ANY($1::text[])",
        list(USDA_MATCHES),
    )
    targets: list[tuple[asyncpg.Record, int, str]] = []
    seen_ids: set[str] = set()
    for row in manual_rows:
        fdc_id = USDA_MATCHES[row["name"]]
        targets.append((row, fdc_id, "reviewed match"))
        seen_ids.add(str(row["id"]))

    if include_all_usda:
        # These foods were imported from this exact FDC record, so no name
        # matching or macro replacement is involved.
        linked_rows = await conn.fetch(
            "SELECT * FROM mt_ingredients WHERE usda_fdc_id IS NOT NULL"
        )
        for row in linked_rows:
            if str(row["id"]) not in seen_ids:
                targets.append((row, row["usda_fdc_id"], "linked FDC record"))
                seen_ids.add(str(row["id"]))

    if not targets:
        print("No matching ingredients found.")
        await conn.close()
        return

    async with httpx.AsyncClient(timeout=20.0) as client:
        for row, fdc_id, match_kind in targets:
            name = row["name"]
            food = await fetch_usda(client, fdc_id)
            per_100g = nutrient_values(food)
            scale = (row["serving_size_g"] or 100.0) / 100.0
            additions = {
                field: round(value * scale, 6)
                for field, value in per_100g.items()
                if row[field] is None
            }
            choline = additions.get("choline_mg")
            print(
                f"{'APPLY' if apply else 'REVIEW'} {name} ← {food.get('description')} "
                f"({match_kind}) | {len(additions)} missing fields "
                f"| choline +{choline if choline is not None else 0:g} mg"
            )
            if not apply or not additions:
                continue

            assignments = ", ".join(
                f"{field} = COALESCE({field}, ${index})"
                for index, field in enumerate(additions, start=1)
            )
            values = list(additions.values()) + [row["id"]]
            await conn.execute(
                f"UPDATE mt_ingredients SET {assignments}, updated_at = NOW() WHERE id = ${len(values)}",
                *values,
            )

    await conn.close()
    print("\nDone." if apply else "\nReview only. Re-run with --apply to write these missing values.")


if __name__ == "__main__":
    asyncio.run(main())
