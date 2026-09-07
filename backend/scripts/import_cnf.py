#!/usr/bin/env python3
"""
Import the Canadian Nutrient File (CNF) into mt_ingredients.

Source: Health Canada, Canadian Nutrient File 2026
        https://open.canada.ca/data/en/dataset/1b6139bd-ed7e-4043-bc28-ff00e10f3109
Licence: Open Government Licence – Canada (free, attribution required)

CNF nutrient amounts are per 100 g of edible portion, which matches this app's
convention, so every imported food gets serving_size_g = 100.

Usage:  python3 import_cnf.py <dir-with-cnf-csvs>  > cnf_import.sql
"""
import csv
import sys
from pathlib import Path

# CNF nutrient code -> mt_ingredients column. Units already align with the
# app's schema (g / mg / mcg) — no conversion needed.
NUTRIENT_MAP = {
    "208": "calories",       "203": "protein_g",   "204": "fat_g",   "205": "carbs_g",
    "291": "fiber_g",        "269": "sugar_g",
    "606": "sat_fat_g",      "605": "trans_fat_g",
    "645": "monounsaturated_fat_g", "646": "polyunsaturated_fat_g",
    "851": "omega3_ala_g",   "629": "omega3_epa_g", "621": "omega3_dha_g",
    "601": "cholesterol_mg",
    # minerals
    "307": "sodium_mg",      "306": "potassium_mg", "301": "calcium_mg",
    "303": "iron_mg",        "304": "magnesium_mg", "305": "phosphorus_mg",
    "309": "zinc_mg",        "312": "copper_mg",    "315": "manganese_mg",
    "317": "selenium_mcg",
    # vitamins  (328 = vitamin D in mcg; 320 = vitamin A as RAE)
    "320": "vitamin_a_mcg",  "319": "retinol_mcg",  "321": "beta_carotene_mcg",
    "401": "vitamin_c_mg",   "328": "vitamin_d_mcg", "323": "vitamin_e_mg",
    "430": "vitamin_k_mcg",  "404": "thiamine_mg",  "405": "riboflavin_mg",
    "406": "niacin_mg",      "410": "pantothenic_acid_mg", "415": "pyridoxine_mg",
    "417": "folate_mcg",     "418": "cobalamin_mcg", "421": "choline_mg",
    # amino acids
    "501": "tryptophan_g",   "502": "threonine_g",  "503": "isoleucine_g",
    "504": "leucine_g",      "505": "lysine_g",     "506": "methionine_g",
    "507": "cystine_g",      "508": "phenylalanine_g", "509": "tyrosine_g",
    "510": "valine_g",       "511": "arginine_g",   "512": "histidine_g",
    "513": "alanine_g",      "514": "aspartic_acid_g", "515": "glutamic_acid_g",
    "516": "glycine_g",      "517": "proline_g",    "518": "serine_g",
    # other
    "262": "caffeine_mg",    "221": "alcohol_g",    "255": "water_g", "207": "ash_g",
}


def sql_str(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def main(src: Path):
    foods = {}
    with open(src / "food_name.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("Food_Description_EN") or "").strip()
            if name:
                foods[row["Food_Code"]] = name

    values = {code: {} for code in foods}
    with open(src / "nutrient_amount.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            col = NUTRIENT_MAP.get(row["Nutrient_Code"])
            if not col:
                continue
            fc = row["Food_Code"]
            if fc not in values:
                continue
            try:
                values[fc][col] = float(row["Nutrient_Amount"])
            except (TypeError, ValueError):
                pass

    cols = ["name", "source", "serving_size_g"] + sorted(set(NUTRIENT_MAP.values()))
    rows, skipped = [], 0
    for fc, name in foods.items():
        v = values[fc]
        if not v.get("calories"):           # no energy value = not usable
            skipped += 1
            continue
        cells = [sql_str(name), "'cnf'", "100"]
        cells += [repr(round(v[c], 4)) if c in v else "NULL"
                  for c in sorted(set(NUTRIENT_MAP.values()))]
        rows.append("(gen_random_uuid()," + ",".join(cells) + ")")

    print("BEGIN;")
    print("DELETE FROM mt_ingredients WHERE source='cnf';")
    collist = ",".join(["id"] + cols)
    for i in range(0, len(rows), 500):
        print(f"INSERT INTO mt_ingredients ({collist}) VALUES")
        print(",\n".join(rows[i:i + 500]) + ";")
    print("COMMIT;")
    print(f"-- {len(rows)} foods imported, {skipped} skipped (no energy value)",
          file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
