#!/usr/bin/env python3
"""
Import Cronometer 'servings' export into Macro Tracker.

Does two things:
  1. WIPES all existing ingredients, meal logs, and meal log items.
  2. Imports every row from servings (2).csv as:
       - A unique food entry in mt_ingredients (source='personal')
       - A diary entry in mt_meal_logs + mt_meal_log_items

Usage (from /backend directory):
    railway run python3 -m scripts.import_servings

Meal group → meal_number mapping:
    Breakfast     → 1
    Lunch         → 2
    Dinner        → 3
    Snacks        → 4
    Uncategorized → 5
"""

import asyncio
import csv
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
BACKEND_DIR   = SCRIPT_DIR.parent
NUTRITION_DIR = BACKEND_DIR.parent / "Nutrition Data"
CSV_PATH      = NUTRITION_DIR / "servings (2).csv"

# Load .env for local runs
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Run with: railway run python3 -m scripts.import_servings")
    sys.exit(1)

DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed. Run: pip install asyncpg --break-system-packages")
    sys.exit(1)

DEFAULT_USER_EMAIL = "jesse@macro.app"

MEAL_NUMBER_MAP = {
    "Breakfast":     1,
    "Lunch":         2,
    "Dinner":        3,
    "Snacks":        4,
    "Uncategorized": 5,
}


# ── Amount → grams ────────────────────────────────────────────────────────────
def parse_grams(amount_str: str):
    """Return float grams if amount_str is parseable, else None."""
    s = amount_str.strip()
    # "30.00 g" or "30 g"
    m = re.match(r"^([\d.]+)\s*g\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # "2.00 oz"
    m = re.match(r"^([\d.]+)\s*oz\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 28.3495
    # "500 mL" / "500 ml"
    m = re.match(r"^([\d.]+)\s*m[lL]\s*$", s)
    if m:
        return float(m.group(1))
    # "2.00 fl oz"
    m = re.match(r"^([\d.]+)\s*fl\.?\s*oz\.?\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 29.5735
    # "2.00 kg"
    m = re.match(r"^([\d.]+)\s*kg\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1000.0
    return None


def _f(val):
    """Parse a CSV cell to float or None."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if v == v else None  # exclude NaN
    except ValueError:
        return None


def _uid():
    return str(uuid.uuid4())


# ── Parse the full CSV ────────────────────────────────────────────────────────
def load_csv():
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


# ── Build unique ingredient records ──────────────────────────────────────────
def build_ingredients(rows):
    """
    For each unique food name, produce one mt_ingredients record.

    Strategy:
    - Collect all occurrences that have gram-parseable amounts.
    - Compute weighted-average per-gram nutrition.
    - Pick the most common gram amount as the canonical serving_size_g.
    - Store all nutrition values AT that serving size (so ratio=1 on first log).
    - For foods that NEVER appear with a parseable gram amount, store
      serving_size_g=NULL and nutrition from the first occurrence as-is
      (macros will still be correct via the snapshot on the log item).
    """
    by_name = defaultdict(list)
    for row in rows:
        name = row["Food Name"].strip()
        grams = parse_grams(row["Amount"])
        by_name[name].append({
            "grams":   grams,
            "amount":  row["Amount"].strip(),
            # core macros
            "calories":       _f(row["Energy (kcal)"]),
            "protein_g":      _f(row["Protein (g)"]),
            "fat_g":          _f(row["Fat (g)"]),
            "carbs_g":        _f(row["Carbs (g)"]),
            "fiber_g":        _f(row["Fiber (g)"]),
            "sugar_g":        _f(row["Sugars (g)"]),
            "sodium_mg":      _f(row["Sodium (mg)"]),
            "cholesterol_mg": _f(row["Cholesterol (mg)"]),
            "sat_fat_g":      _f(row["Saturated (g)"]),
            "trans_fat_g":    _f(row["Trans-Fats (g)"]),
            "mono_fat_g":     _f(row["Monounsaturated (g)"]),
            "poly_fat_g":     _f(row["Polyunsaturated (g)"]),
            "omega3_g":       _f(row["Omega-3 (g)"]),
            "omega3_ala_g":   _f(row["ALA (g)"]),
            "omega3_dha_g":   _f(row["DHA (g)"]),
            "omega3_epa_g":   _f(row["EPA (g)"]),
            "omega6_g":       _f(row["Omega-6 (g)"]),
            "omega6_aa_g":    _f(row["AA (g)"]),
            "omega6_la_g":    _f(row["LA (g)"]),
            "insoluble_fiber_g": _f(row["Insoluble Fiber (g)"]),
            "soluble_fiber_g":   _f(row["Soluble Fiber (g)"]),
            # vitamins
            "vitamin_a_mcg":       _f(row["Vitamin A (µg)"]),
            "vitamin_c_mg":        _f(row["Vitamin C (mg)"]),
            "vitamin_d_iu":        _f(row["Vitamin D (IU)"]),
            "vitamin_e_mg":        _f(row["Vitamin E (mg)"]),
            "vitamin_k_mcg":       _f(row["Vitamin K (µg)"]),
            "thiamine_mg":         _f(row["B1 (Thiamine) (mg)"]),
            "riboflavin_mg":       _f(row["B2 (Riboflavin) (mg)"]),
            "niacin_mg":           _f(row["B3 (Niacin) (mg)"]),
            "pantothenic_acid_mg": _f(row["B5 (Pantothenic Acid) (mg)"]),
            "pyridoxine_mg":       _f(row["B6 (Pyridoxine) (mg)"]),
            "cobalamin_mcg":       _f(row["B12 (Cobalamin) (µg)"]),
            "folate_mcg":          _f(row["Folate (µg)"]),
            "beta_carotene_mcg":   _f(row["Beta-carotene (µg)"]),
            # minerals
            "calcium_mg":   _f(row["Calcium (mg)"]),
            "copper_mg":    _f(row["Copper (mg)"]),
            "iron_mg":      _f(row["Iron (mg)"]),
            "magnesium_mg": _f(row["Magnesium (mg)"]),
            "manganese_mg": _f(row["Manganese (mg)"]),
            "phosphorus_mg":_f(row["Phosphorus (mg)"]),
            "potassium_mg": _f(row["Potassium (mg)"]),
            "selenium_mcg": _f(row["Selenium (µg)"]),
            "zinc_mg":      _f(row["Zinc (mg)"]),
            # other
            "caffeine_mg":  _f(row["Caffeine (mg)"]),
            "water_g":      _f(row["Water (g)"]),
            "alcohol_g":    _f(row["Alcohol (g)"]),
            "oxalate_mg":   _f(row["Oxalate (mg)"]),
            "phytate_mg":   _f(row["Phytate (mg)"]),
            # amino acids
            "cystine_g":      _f(row["Cystine (g)"]),
            "histidine_g":    _f(row["Histidine (g)"]),
            "isoleucine_g":   _f(row["Isoleucine (g)"]),
            "leucine_g":      _f(row["Leucine (g)"]),
            "lysine_g":       _f(row["Lysine (g)"]),
            "methionine_g":   _f(row["Methionine (g)"]),
            "phenylalanine_g":_f(row["Phenylalanine (g)"]),
            "threonine_g":    _f(row["Threonine (g)"]),
            "tryptophan_g":   _f(row["Tryptophan (g)"]),
            "tyrosine_g":     _f(row["Tyrosine (g)"]),
            "valine_g":       _f(row["Valine (g)"]),
        })

    ingredients = {}  # name → ingredient dict

    for name, entries in by_name.items():
        gram_entries = [e for e in entries if e["grams"] and e["grams"] >= 0.5]

        if gram_entries:
            # Weighted average per gram across all gram-parseable entries
            def w_avg(key):
                pairs = [
                    (e[key] / e["grams"], e["grams"])
                    for e in gram_entries
                    if e[key] is not None
                ]
                if not pairs:
                    return None
                total_w = sum(w for _, w in pairs)
                return sum(v * w for v, w in pairs) / total_w

            # Most common gram amount → canonical serving
            gram_counts = Counter(round(e["grams"]) for e in gram_entries)
            typical_g = float(gram_counts.most_common(1)[0][0])

            def at_serving(key):
                v = w_avg(key)
                return round(v * typical_g, 4) if v is not None else None

            # vitamin D: IU → mcg  (1 IU = 0.025 mcg)
            vd_per_g = w_avg("vitamin_d_iu")
            vitamin_d_mcg = round(vd_per_g * typical_g * 0.025, 4) if vd_per_g is not None else None

            ingredients[name] = {
                "id":               _uid(),
                "name":             name,
                "source":           "personal",
                "serving_size_g":   typical_g,
                "serving_size_desc": f"{int(typical_g)} g",
                # macros at serving
                "calories":       at_serving("calories")    or 0.0,
                "protein_g":      at_serving("protein_g")   or 0.0,
                "fat_g":          at_serving("fat_g")        or 0.0,
                "carbs_g":        at_serving("carbs_g")      or 0.0,
                "fiber_g":        at_serving("fiber_g"),
                "sugar_g":        at_serving("sugar_g"),
                "sodium_mg":      at_serving("sodium_mg"),
                "cholesterol_mg": at_serving("cholesterol_mg"),
                "sat_fat_g":      at_serving("sat_fat_g"),
                "trans_fat_g":    at_serving("trans_fat_g"),
                "mono_fat_g":     at_serving("mono_fat_g"),
                "poly_fat_g":     at_serving("poly_fat_g"),
                "omega3_ala_g":   at_serving("omega3_ala_g"),
                "omega3_dha_g":   at_serving("omega3_dha_g"),
                "omega3_epa_g":   at_serving("omega3_epa_g"),
                "omega6_aa_g":    at_serving("omega6_aa_g"),
                "omega6_la_g":    at_serving("omega6_la_g"),
                "insoluble_fiber_g": at_serving("insoluble_fiber_g"),
                "soluble_fiber_g":   at_serving("soluble_fiber_g"),
                # vitamins
                "vitamin_a_mcg":       at_serving("vitamin_a_mcg"),
                "vitamin_c_mg":        at_serving("vitamin_c_mg"),
                "vitamin_d_mcg":       vitamin_d_mcg,
                "vitamin_e_mg":        at_serving("vitamin_e_mg"),
                "vitamin_k_mcg":       at_serving("vitamin_k_mcg"),
                "thiamine_mg":         at_serving("thiamine_mg"),
                "riboflavin_mg":       at_serving("riboflavin_mg"),
                "niacin_mg":           at_serving("niacin_mg"),
                "pantothenic_acid_mg": at_serving("pantothenic_acid_mg"),
                "pyridoxine_mg":       at_serving("pyridoxine_mg"),
                "cobalamin_mcg":       at_serving("cobalamin_mcg"),
                "folate_mcg":          at_serving("folate_mcg"),
                "beta_carotene_mcg":   at_serving("beta_carotene_mcg"),
                # minerals
                "calcium_mg":   at_serving("calcium_mg"),
                "copper_mg":    at_serving("copper_mg"),
                "iron_mg":      at_serving("iron_mg"),
                "magnesium_mg": at_serving("magnesium_mg"),
                "manganese_mg": at_serving("manganese_mg"),
                "phosphorus_mg":at_serving("phosphorus_mg"),
                "potassium_mg": at_serving("potassium_mg"),
                "selenium_mcg": at_serving("selenium_mcg"),
                "zinc_mg":      at_serving("zinc_mg"),
                # other
                "caffeine_mg": at_serving("caffeine_mg"),
                "water_g":     at_serving("water_g"),
                "alcohol_g":   at_serving("alcohol_g"),
                "oxalate_mg":  at_serving("oxalate_mg"),
                "phytate_mg":  at_serving("phytate_mg"),
                # amino acids
                "cystine_g":       at_serving("cystine_g"),
                "histidine_g":     at_serving("histidine_g"),
                "isoleucine_g":    at_serving("isoleucine_g"),
                "leucine_g":       at_serving("leucine_g"),
                "lysine_g":        at_serving("lysine_g"),
                "methionine_g":    at_serving("methionine_g"),
                "phenylalanine_g": at_serving("phenylalanine_g"),
                "threonine_g":     at_serving("threonine_g"),
                "tryptophan_g":    at_serving("tryptophan_g"),
                "tyrosine_g":      at_serving("tyrosine_g"),
                "valine_g":        at_serving("valine_g"),
            }
        else:
            # No gram entries — use first occurrence as-is (serving_size_g=NULL)
            e = entries[0]
            vd_iu = e.get("vitamin_d_iu")
            vitamin_d_mcg = round(vd_iu * 0.025, 4) if vd_iu is not None else None

            ingredients[name] = {
                "id":               _uid(),
                "name":             name,
                "source":           "personal",
                "serving_size_g":   None,
                "serving_size_desc": e["amount"],
                "calories":       e["calories"]    or 0.0,
                "protein_g":      e["protein_g"]   or 0.0,
                "fat_g":          e["fat_g"]        or 0.0,
                "carbs_g":        e["carbs_g"]      or 0.0,
                "fiber_g":        e["fiber_g"],
                "sugar_g":        e["sugar_g"],
                "sodium_mg":      e["sodium_mg"],
                "cholesterol_mg": e["cholesterol_mg"],
                "sat_fat_g":      e["sat_fat_g"],
                "trans_fat_g":    e["trans_fat_g"],
                "mono_fat_g":     e["mono_fat_g"],
                "poly_fat_g":     e["poly_fat_g"],
                "omega3_ala_g":   e["omega3_ala_g"],
                "omega3_dha_g":   e["omega3_dha_g"],
                "omega3_epa_g":   e["omega3_epa_g"],
                "omega6_aa_g":    e["omega6_aa_g"],
                "omega6_la_g":    e["omega6_la_g"],
                "insoluble_fiber_g": e["insoluble_fiber_g"],
                "soluble_fiber_g":   e["soluble_fiber_g"],
                "vitamin_a_mcg":       e["vitamin_a_mcg"],
                "vitamin_c_mg":        e["vitamin_c_mg"],
                "vitamin_d_mcg":       vitamin_d_mcg,
                "vitamin_e_mg":        e["vitamin_e_mg"],
                "vitamin_k_mcg":       e["vitamin_k_mcg"],
                "thiamine_mg":         e["thiamine_mg"],
                "riboflavin_mg":       e["riboflavin_mg"],
                "niacin_mg":           e["niacin_mg"],
                "pantothenic_acid_mg": e["pantothenic_acid_mg"],
                "pyridoxine_mg":       e["pyridoxine_mg"],
                "cobalamin_mcg":       e["cobalamin_mcg"],
                "folate_mcg":          e["folate_mcg"],
                "beta_carotene_mcg":   e["beta_carotene_mcg"],
                "calcium_mg":   e["calcium_mg"],
                "copper_mg":    e["copper_mg"],
                "iron_mg":      e["iron_mg"],
                "magnesium_mg": e["magnesium_mg"],
                "manganese_mg": e["manganese_mg"],
                "phosphorus_mg":e["phosphorus_mg"],
                "potassium_mg": e["potassium_mg"],
                "selenium_mcg": e["selenium_mcg"],
                "zinc_mg":      e["zinc_mg"],
                "caffeine_mg":  e["caffeine_mg"],
                "water_g":      e["water_g"],
                "alcohol_g":    e["alcohol_g"],
                "oxalate_mg":   e["oxalate_mg"],
                "phytate_mg":   e["phytate_mg"],
                "cystine_g":       e["cystine_g"],
                "histidine_g":     e["histidine_g"],
                "isoleucine_g":    e["isoleucine_g"],
                "leucine_g":       e["leucine_g"],
                "lysine_g":        e["lysine_g"],
                "methionine_g":    e["methionine_g"],
                "phenylalanine_g": e["phenylalanine_g"],
                "threonine_g":     e["threonine_g"],
                "tryptophan_g":    e["tryptophan_g"],
                "tyrosine_g":      e["tyrosine_g"],
                "valine_g":        e["valine_g"],
            }

    return ingredients  # name → ingredient dict


# ── Build meal log structures ─────────────────────────────────────────────────
def build_meal_logs(rows, ingredients):
    """
    Returns:
        meal_logs  — list of dicts for mt_meal_logs
        meal_items — list of dicts for mt_meal_log_items
    """
    # Group rows by (date, group)
    by_meal = defaultdict(list)
    for row in rows:
        key = (row["Day"].strip(), row["Group"].strip())
        by_meal[key].append(row)

    meal_logs  = []
    meal_items = []

    for (day_str, group), meal_rows in sorted(by_meal.items()):
        meal_number = MEAL_NUMBER_MAP.get(group, 5)
        meal_id     = _uid()

        # Parse the time from the first item in this meal
        time_str = meal_rows[0]["Time"].strip() if meal_rows else "12:00 PM"
        try:
            logged_dt = datetime.strptime(f"{day_str} {time_str}", "%Y-%m-%d %I:%M %p")
        except ValueError:
            logged_dt = datetime.strptime(day_str, "%Y-%m-%d")

        total_cal  = 0.0
        total_prot = 0.0
        total_fat  = 0.0
        total_carb = 0.0
        total_sod  = 0.0
        total_chol = 0.0

        for row in meal_rows:
            food_name = row["Food Name"].strip()
            ing       = ingredients.get(food_name)
            ing_id    = ing["id"] if ing else None

            # Snapshot macros — these are the values FROM the CSV for this specific log entry
            cal  = _f(row["Energy (kcal)"]) or 0.0
            prot = _f(row["Protein (g)"])   or 0.0
            fat  = _f(row["Fat (g)"])        or 0.0
            carb = _f(row["Carbs (g)"])      or 0.0
            sod  = _f(row["Sodium (mg)"])    or 0.0
            chol = _f(row["Cholesterol (mg)"]) or 0.0

            total_cal  += cal
            total_prot += prot
            total_fat  += fat
            total_carb += carb
            total_sod  += sod
            total_chol += chol

            # quantity_g: use parsed grams; fall back to ingredient's serving_size_g; then 100
            grams = parse_grams(row["Amount"].strip())
            if grams is None:
                grams = ing["serving_size_g"] if ing and ing["serving_size_g"] else 100.0

            # Parse item timestamp
            t_str = row["Time"].strip()
            try:
                item_dt = datetime.strptime(f"{day_str} {t_str}", "%Y-%m-%d %I:%M %p")
            except ValueError:
                item_dt = logged_dt

            meal_items.append({
                "id":            _uid(),
                "meal_log_id":   meal_id,
                "ingredient_id": ing_id,
                "quantity_g":    round(grams, 2),
                "display_name":  food_name,
                "calories":      round(cal,  2),
                "protein_g":     round(prot, 2),
                "fat_g":         round(fat,  2),
                "carbs_g":       round(carb, 2),
                "sodium_mg":     round(sod,  2),
                "cholesterol_mg":round(chol, 2),
                "logged_at":     item_dt,
            })

        meal_logs.append({
            "id":                  meal_id,
            "log_date":            day_str,
            "meal_number":         meal_number,
            "logged_at":           logged_dt,
            "total_calories":      round(total_cal,  2),
            "total_protein_g":     round(total_prot, 2),
            "total_fat_g":         round(total_fat,  2),
            "total_carbs_g":       round(total_carb, 2),
            "total_sodium_mg":     round(total_sod,  2),
            "total_cholesterol_mg":round(total_chol, 2),
        })

    return meal_logs, meal_items


# ── Database helpers ──────────────────────────────────────────────────────────
async def get_or_create_user(conn) -> str:
    row = await conn.fetchrow(
        "SELECT id FROM mt_users WHERE email=$1", DEFAULT_USER_EMAIL
    )
    if row:
        return row["id"]
    user_id = _uid()
    await conn.execute(
        "INSERT INTO mt_users (id, email, name) VALUES ($1,$2,$3)",
        user_id, DEFAULT_USER_EMAIL, "Jesse"
    )
    return user_id


async def wipe_data(conn, user_id: str):
    """Delete all meal logs (cascade removes items) and all ingredients."""
    print("🗑️  Wiping existing meal logs…")
    await conn.execute("DELETE FROM mt_meal_logs WHERE user_id=$1", user_id)

    print("🗑️  Wiping existing personal/custom ingredients (keeping restaurant items)…")
    await conn.execute("DELETE FROM mt_ingredients WHERE source NOT IN ('restaurant')")
    print("   ✓ Clean slate ready")


def _ing_row(ing):
    """Return a tuple of values for one ingredient INSERT."""
    return (
        ing["id"], ing["source"], ing["name"],
        ing["serving_size_g"], ing["serving_size_desc"],
        ing["calories"], ing["protein_g"], ing["fat_g"], ing["carbs_g"],
        ing["fiber_g"], ing["sugar_g"], ing["sodium_mg"], ing["cholesterol_mg"],
        ing["sat_fat_g"], ing["trans_fat_g"], ing["mono_fat_g"], ing["poly_fat_g"],
        ing["omega3_ala_g"], ing["omega3_dha_g"], ing["omega3_epa_g"],
        ing["omega6_aa_g"], ing["omega6_la_g"],
        ing["insoluble_fiber_g"], ing["soluble_fiber_g"],
        ing["vitamin_a_mcg"], ing["vitamin_c_mg"], ing["vitamin_d_mcg"],
        ing["vitamin_e_mg"], ing["vitamin_k_mcg"],
        ing["thiamine_mg"], ing["riboflavin_mg"], ing["niacin_mg"],
        ing["pantothenic_acid_mg"], ing["pyridoxine_mg"], ing["cobalamin_mcg"],
        ing["folate_mcg"], ing["beta_carotene_mcg"],
        ing["calcium_mg"], ing["copper_mg"], ing["iron_mg"], ing["magnesium_mg"],
        ing["manganese_mg"], ing["phosphorus_mg"], ing["potassium_mg"],
        ing["selenium_mcg"], ing["zinc_mg"],
        ing["caffeine_mg"], ing["water_g"], ing["alcohol_g"],
        ing["oxalate_mg"], ing["phytate_mg"],
        ing["cystine_g"], ing["histidine_g"], ing["isoleucine_g"], ing["leucine_g"],
        ing["lysine_g"], ing["methionine_g"], ing["phenylalanine_g"], ing["threonine_g"],
        ing["tryptophan_g"], ing["tyrosine_g"], ing["valine_g"],
    )


ING_SQL = """
    INSERT INTO mt_ingredients (
        id, source, name, serving_size_g, serving_size_desc,
        calories, protein_g, fat_g, carbs_g,
        fiber_g, sugar_g, sodium_mg, cholesterol_mg,
        sat_fat_g, trans_fat_g, monounsaturated_fat_g, polyunsaturated_fat_g,
        omega3_ala_g, omega3_dha_g, omega3_epa_g,
        omega6_aa_g, omega6_la_g,
        insoluble_fiber_g, soluble_fiber_g,
        vitamin_a_mcg, vitamin_c_mg, vitamin_d_mcg, vitamin_e_mg, vitamin_k_mcg,
        thiamine_mg, riboflavin_mg, niacin_mg, pantothenic_acid_mg,
        pyridoxine_mg, cobalamin_mcg, folate_mcg, beta_carotene_mcg,
        calcium_mg, copper_mg, iron_mg, magnesium_mg, manganese_mg,
        phosphorus_mg, potassium_mg, selenium_mcg, zinc_mg,
        caffeine_mg, water_g, alcohol_g, oxalate_mg, phytate_mg,
        cystine_g, histidine_g, isoleucine_g, leucine_g, lysine_g,
        methionine_g, phenylalanine_g, threonine_g, tryptophan_g,
        tyrosine_g, valine_g,
        created_at, updated_at
    ) VALUES (
        $1,$2,$3,$4,$5,
        $6,$7,$8,$9,
        $10,$11,$12,$13,
        $14,$15,$16,$17,
        $18,$19,$20,
        $21,$22,
        $23,$24,
        $25,$26,$27,$28,$29,
        $30,$31,$32,$33,
        $34,$35,$36,$37,
        $38,$39,$40,$41,$42,
        $43,$44,$45,$46,
        $47,$48,$49,$50,$51,
        $52,$53,$54,$55,$56,
        $57,$58,$59,$60,
        $61,$62,
        NOW(), NOW()
    )
"""

MEAL_LOG_SQL = """
    INSERT INTO mt_meal_logs (
        id, user_id, log_date, meal_number, logged_at,
        total_calories, total_protein_g, total_fat_g, total_carbs_g,
        total_sodium_mg, total_cholesterol_mg
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
    ON CONFLICT (user_id, log_date, meal_number) DO NOTHING
"""

ITEM_SQL = """
    INSERT INTO mt_meal_log_items (
        id, meal_log_id, ingredient_id,
        quantity_g, display_name,
        calories, protein_g, fat_g, carbs_g,
        sodium_mg, cholesterol_mg, logged_at
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
"""

CHUNK = 200  # rows per executemany call


async def insert_ingredients(conn, ingredients: dict):
    print(f"🥦  Inserting {len(ingredients)} unique foods in chunks of {CHUNK}…")
    rows = [_ing_row(ing) for ing in ingredients.values()]
    count = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        await conn.executemany(ING_SQL, chunk)
        count += len(chunk)
        print(f"   … {count} / {len(rows)} foods inserted")
    print(f"   ✓ {count} ingredients imported")


async def insert_meal_logs(conn, user_id: str, meal_logs: list, meal_items: list):
    print(f"📅  Inserting {len(meal_logs)} meal logs + {len(meal_items)} items…")

    # Build flat tuples for executemany
    log_rows = [
        (
            ml["id"], user_id, date.fromisoformat(ml["log_date"]),
            ml["meal_number"], ml["logged_at"],
            ml["total_calories"], ml["total_protein_g"], ml["total_fat_g"], ml["total_carbs_g"],
            ml["total_sodium_mg"], ml["total_cholesterol_mg"],
        )
        for ml in meal_logs
    ]
    item_rows = [
        (
            it["id"], it["meal_log_id"], it["ingredient_id"],
            it["quantity_g"], it["display_name"],
            it["calories"], it["protein_g"], it["fat_g"], it["carbs_g"],
            it["sodium_mg"], it["cholesterol_mg"], it["logged_at"],
        )
        for it in meal_items
    ]

    # Insert meal logs in chunks
    for i in range(0, len(log_rows), CHUNK):
        await conn.executemany(MEAL_LOG_SQL, log_rows[i:i + CHUNK])
    print(f"   ✓ {len(log_rows)} meal logs inserted")

    # Insert items in chunks
    inserted = 0
    for i in range(0, len(item_rows), CHUNK):
        await conn.executemany(ITEM_SQL, item_rows[i:i + CHUNK])
        inserted += len(item_rows[i:i + CHUNK])
        if inserted % 2000 == 0:
            print(f"   … {inserted} / {len(item_rows)} items inserted")
    print(f"   ✓ {len(item_rows)} food items inserted")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    if not CSV_PATH.exists():
        print(f"❌ CSV not found at {CSV_PATH}")
        sys.exit(1)

    print(f"📂 Reading {CSV_PATH.name}…")
    rows = load_csv()
    print(f"   → {len(rows):,} diary entries")

    print("🔬 Processing unique foods…")
    ingredients = build_ingredients(rows)
    print(f"   → {len(ingredients):,} unique foods")

    print("📋 Building meal log structures…")
    meal_logs, meal_items = build_meal_logs(rows, ingredients)
    print(f"   → {len(meal_logs):,} meals across {len({ml['log_date'] for ml in meal_logs}):,} days")

    print("🔌 Connecting to database…")
    conn = await asyncpg.connect(
        DATABASE_URL,
        server_settings={"tcp_keepalives_idle": "60"},
        command_timeout=300,
    )

    try:
        user_id = await get_or_create_user(conn)
        print(f"   ✓ User: {DEFAULT_USER_EMAIL} ({user_id})")

        await wipe_data(conn, user_id)
        await insert_ingredients(conn, ingredients)
        await insert_meal_logs(conn, user_id, meal_logs, meal_items)

    finally:
        await conn.close()

    print()
    print("🎉 Import complete!")
    print(f"   {len(ingredients):,} foods in library")
    print(f"   {len(meal_logs):,} meal logs")
    print(f"   {len(meal_items):,} food items")


if __name__ == "__main__":
    asyncio.run(main())
