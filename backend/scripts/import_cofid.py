#!/usr/bin/env python3
"""
Import McCance & Widdowson's Composition of Foods Integrated Dataset (CoFID)
into mt_ingredients.

Source:  Public Health England / OHID, CoFID 2021
         https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid
Licence: Open Government Licence v3.0 (free, attribution required)

All CoFID values are per 100 g of food, matching this app's convention, so
every imported food gets serving_size_g = 100.

Notes on choices made here:
  • Fibre uses AOAC (not the older Englyst/NSP figure) so it is comparable
    with USDA and CNF data already in the database.
  • 'N' means "not analysed" -> NULL (never 0, which would be a false claim).
  • 'Tr' means trace -> 0.
  • Vitamin A uses Retinol Equivalent, the only vitamin A total CoFID gives.

Usage:  python3 import_cofid.py <cofid.xlsx>  > cofid_import.sql
"""
import sys
from pathlib import Path

import openpyxl

HEADER_ROWS = 3          # row1 titles, row2 codes, row3 descriptions

# sheet -> { column short-code : mt_ingredients column }
SHEETS = {
    "1.3 Proximates": {
        "KCALS": "calories", "PROT": "protein_g", "FAT": "fat_g", "CHO": "carbs_g",
        "WATER": "water_g", "TOTSUG": "sugar_g", "AOACFIB": "fiber_g",
        "ALCO": "alcohol_g", "CHOL": "cholesterol_mg",
        "SATFOD": "sat_fat_g", "MONOFOD": "monounsaturated_fat_g",
        "POLYFOD": "polyunsaturated_fat_g", "FODTRANS": "trans_fat_g",
        "GLUC": "glucose_g", "GALACT": "galactose_g", "FRUCT": "fructose_g",
        "SUCR": "sucrose_g", "MALT": "maltose_g", "LACT": "lactose_g",
    },
    "1.4 Inorganics": {
        "NA": "sodium_mg", "K": "potassium_mg", "CA": "calcium_mg",
        "MG": "magnesium_mg", "P": "phosphorus_mg", "FE": "iron_mg",
        "CU": "copper_mg", "ZN": "zinc_mg", "MN": "manganese_mg",
        "SE": "selenium_mcg", "I": "iodine_mcg",
    },
    "1.5 Vitamins": {
        "RET": "retinol_mcg", "CAREQU": "beta_carotene_mcg",
        "RETEQU": "vitamin_a_mcg", "VITD": "vitamin_d_mcg", "VITE": "vitamin_e_mg",
        "VITK1": "vitamin_k_mcg", "THIA": "thiamine_mg", "RIBO": "riboflavin_mg",
        "NIAC": "niacin_mg", "VITB6": "pyridoxine_mg", "VITB12": "cobalamin_mcg",
        "FOLT": "folate_mcg", "PANTO": "pantothenic_acid_mg", "BIOT": "biotin_mcg",
        "VITC": "vitamin_c_mg",
    },
    "1.12 (PUFA per 100gFood)": {
        "FOD18:2cn6": "omega6_la_g", "FOD18:3cn3": "omega3_ala_g",
        "FOD20:4cn6": "omega6_aa_g", "FOD20:5cn3": "omega3_epa_g",
        "FOD22:6cn3": "omega3_dha_g",
    },
}


def parse(v):
    """CoFID cell -> float | None.  'N'=not analysed (None), 'Tr'=trace (0)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s.upper() == "N":
        return None
    if s.lower().startswith("tr"):
        return 0.0
    s = s.strip("()")                     # (12) = estimated value
    try:
        return float(s)
    except ValueError:
        return None


def main(xlsx: Path):
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    names, data = {}, {}

    for sheet, colmap in SHEETS.items():
        ws = wb[sheet]
        rows = ws.iter_rows(values_only=True)
        next(rows)                                   # titles
        codes = [str(c).strip() if c else "" for c in next(rows)]
        next(rows)                                   # descriptions
        idx = {code: i for i, code in enumerate(codes) if code in colmap}

        for row in rows:
            if not row or not row[0]:
                continue
            fc = str(row[0]).strip()
            if sheet == "1.3 Proximates" and row[1]:
                names[fc] = str(row[1]).strip()
            bucket = data.setdefault(fc, {})
            for code, i in idx.items():
                val = parse(row[i]) if i < len(row) else None
                if val is not None:
                    bucket[colmap[code]] = val

    cols = sorted({c for m in SHEETS.values() for c in m.values()})
    rows_sql, skipped = [], 0
    for fc, name in names.items():
        v = data.get(fc, {})
        if not v.get("calories"):
            skipped += 1
            continue
        # These four are NOT NULL in the schema. CoFID 'N' (not analysed) has to
        # become 0 for them; every other nutrient keeps NULL to stay honest about
        # the difference between "measured as zero" and "never measured".
        REQUIRED = {"calories", "protein_g", "fat_g", "carbs_g"}
        cells = ["'" + name.replace("'", "''") + "'", "'cofid'", "100"]
        cells += [repr(round(v[c], 4)) if c in v
                  else ("0" if c in REQUIRED else "NULL") for c in cols]
        rows_sql.append("(gen_random_uuid()," + ",".join(cells) + ")")

    collist = ",".join(["id", "name", "source", "serving_size_g"] + cols)
    print("BEGIN;")
    print("DELETE FROM mt_ingredients WHERE source='cofid';")
    for i in range(0, len(rows_sql), 500):
        print(f"INSERT INTO mt_ingredients ({collist}) VALUES")
        print(",\n".join(rows_sql[i:i + 500]) + ";")
    print("COMMIT;")
    print(f"-- {len(rows_sql)} foods, {skipped} skipped (no energy value)", file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
