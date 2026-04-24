#!/usr/bin/env python3
"""
export_personal_foods.py — Export all personal foods with full nutrient detail.

Usage:
    API_URL=https://macro-tracker-production-207a.up.railway.app \
        python3 scripts/export_personal_foods.py

Optional flags:
    --source custom|personal|restaurant   (default: personal)
    --out    path/to/output.csv           (default: personal_foods_<date>.csv)
"""

import argparse
import csv
import os
import sys
from datetime import date
import urllib.request
import json

# ── Nutrient columns in display order ────────────────────────────────────────
NUTRIENT_COLS = [
    # Macros
    "calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g",
    "sat_fat_g", "trans_fat_g", "cholesterol_mg", "sodium_mg", "potassium_mg",
    # Vitamins
    "vitamin_a_mcg", "vitamin_c_mg", "vitamin_d_mcg", "vitamin_e_mg",
    "vitamin_k_mcg", "thiamine_mg", "riboflavin_mg", "niacin_mg",
    "pantothenic_acid_mg", "pyridoxine_mg", "cobalamin_mcg", "biotin_mcg",
    "folate_mcg", "choline_mg", "retinol_mcg", "alpha_carotene_mcg",
    "beta_carotene_mcg", "beta_cryptoxanthin_mcg", "lutein_zeaxanthin_mcg",
    "lycopene_mcg", "beta_tocopherol_mg", "delta_tocopherol_mg",
    "gamma_tocopherol_mg",
    # Minerals
    "calcium_mg", "iron_mg", "magnesium_mg", "phosphorus_mg", "zinc_mg",
    "copper_mg", "manganese_mg", "selenium_mcg", "chromium_mcg", "iodine_mcg",
    "molybdenum_mcg", "fluoride_mg",
    # Amino acids
    "alanine_g", "arginine_g", "aspartic_acid_g", "cystine_g",
    "glutamic_acid_g", "glycine_g", "histidine_g", "hydroxyproline_g",
    "isoleucine_g", "leucine_g", "lysine_g", "methionine_g",
    "phenylalanine_g", "proline_g", "serine_g", "threonine_g",
    "tryptophan_g", "tyrosine_g", "valine_g",
    # Fatty acids
    "monounsaturated_fat_g", "polyunsaturated_fat_g", "omega3_ala_g",
    "omega3_epa_g", "omega3_dha_g", "omega6_la_g", "omega6_aa_g",
    "phytosterol_mg",
    # Carb / other
    "soluble_fiber_g", "insoluble_fiber_g", "fructose_g", "galactose_g",
    "glucose_g", "lactose_g", "maltose_g", "sucrose_g", "oxalate_mg",
    "phytate_mg", "caffeine_mg", "water_g", "ash_g", "alcohol_g",
    "beta_hydroxybutyrate_g",
]

ID_COLS = ["id", "name", "brand", "source", "serving_size_g", "serving_size_desc"]


def fetch_foods(base_url: str, source: str) -> list[dict]:
    url = f"{base_url.rstrip('/')}/api/v1/foods/?source={source}&limit=10000"
    print(f"  Fetching {url} …")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Export foods to CSV")
    parser.add_argument("--source", default="personal",
                        choices=["personal", "custom", "restaurant"],
                        help="Which source group to export (default: personal)")
    parser.add_argument("--out", default=None,
                        help="Output CSV path (default: <source>_foods_<date>.csv)")
    args = parser.parse_args()

    base_url = os.environ.get("API_URL", "").strip()
    if not base_url:
        print("ERROR: Set API_URL environment variable, e.g.:")
        print("  API_URL=https://macro-tracker-production-207a.up.railway.app python3 scripts/export_personal_foods.py")
        sys.exit(1)

    out_path = args.out or f"{args.source}_foods_{date.today().isoformat()}.csv"

    print(f"\n{'─'*55}")
    print(f"  Source : {args.source}")
    print(f"  Output : {out_path}")
    print(f"{'─'*55}")

    foods = fetch_foods(base_url, args.source)

    if not foods:
        print("\nNo foods returned — nothing to export.")
        sys.exit(0)

    # For source=custom the API returns custom+personal combined;
    # filter to just the requested source if user asked for "custom" alone.
    if args.source == "custom":
        foods = [f for f in foods if f.get("source") == "custom"]

    print(f"  Records: {len(foods)}")

    all_cols = ID_COLS + NUTRIENT_COLS

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_cols, extrasaction="ignore")
        writer.writeheader()
        for food in sorted(foods, key=lambda f: f.get("name", "").lower()):
            writer.writerow({col: food.get(col, "") for col in all_cols})

    print(f"\n✓ Wrote {len(foods)} rows → {out_path}")
    print()

    # Quick summary of nutrient coverage
    covered = {
        col: sum(1 for f in foods if f.get(col) not in (None, ""))
        for col in NUTRIENT_COLS
    }
    filled = [c for c, n in covered.items() if n > 0]
    empty  = [c for c, n in covered.items() if n == 0]
    print(f"  Nutrient fields with data : {len(filled)}/{len(NUTRIENT_COLS)}")
    if empty:
        print(f"  Fields with no data       : {', '.join(empty[:10])}"
              + (" …" if len(empty) > 10 else ""))


if __name__ == "__main__":
    main()
