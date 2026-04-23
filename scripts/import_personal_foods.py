#!/usr/bin/env python3
"""
import_personal_foods.py — zero external dependencies (stdlib only)
────────────────────────────────────────────────────────────────────
Reads personal_foods.csv (Cronometer export) and bulk-imports every
unique food into the Macro Tracker database via the REST API.

Strategy
────────
• Foods with at least one gram- or oz-based Amount entry are normalised to
  per-100 g by averaging all gram-based observations. serving_size_g = 100.
• Foods with only unit-based amounts (tbsp, medium, full recipe, …) are
  stored using the first occurrence as-is. serving_size_desc = amount string.
• source = "personal" — distinct from "usda", "custom", "restaurant".
• Vitamin D (IU) → mcg:  multiply by 0.025.
• Existing personal foods are skipped unless --overwrite is passed.

Usage
─────
  # Point at your Railway deployment
  API_URL=https://<app>.up.railway.app python scripts/import_personal_foods.py

  # Point at a local dev server
  API_URL=http://localhost:8000 python scripts/import_personal_foods.py

  # Dry run — see what would be imported without touching the DB
  python scripts/import_personal_foods.py --dry-run

  # Overwrite existing personal foods
  python scripts/import_personal_foods.py --overwrite

  # Only import first N foods (useful for testing)
  python scripts/import_personal_foods.py --limit 10
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH = Path(__file__).parent.parent / "Nutrition data" / "personal_foods.csv"
API_URL  = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

# ── Column → ingredient field mapping ────────────────────────────────────────
COLUMN_MAP = {
    "Energy (kcal)":              "calories",
    "Protein (g)":                "protein_g",
    "Fat (g)":                    "fat_g",
    "Carbs (g)":                  "carbs_g",
    "Fiber (g)":                  "fiber_g",
    "Insoluble Fiber (g)":        "insoluble_fiber_g",
    "Soluble Fiber (g)":          "soluble_fiber_g",
    "Sugars (g)":                 "sugar_g",
    "Saturated (g)":              "sat_fat_g",
    "Trans-Fats (g)":             "trans_fat_g",
    "Monounsaturated (g)":        "monounsaturated_fat_g",
    "Polyunsaturated (g)":        "polyunsaturated_fat_g",
    "Cholesterol (mg)":           "cholesterol_mg",
    "Sodium (mg)":                "sodium_mg",
    "Potassium (mg)":             "potassium_mg",
    "Calcium (mg)":               "calcium_mg",
    "Iron (mg)":                  "iron_mg",
    "Magnesium (mg)":             "magnesium_mg",
    "Phosphorus (mg)":            "phosphorus_mg",
    "Zinc (mg)":                  "zinc_mg",
    "Copper (mg)":                "copper_mg",
    "Manganese (mg)":             "manganese_mg",
    "Selenium (µg)":              "selenium_mcg",
    "B1 (Thiamine) (mg)":         "thiamine_mg",
    "B2 (Riboflavin) (mg)":       "riboflavin_mg",
    "B3 (Niacin) (mg)":           "niacin_mg",
    "B5 (Pantothenic Acid) (mg)": "pantothenic_acid_mg",
    "B6 (Pyridoxine) (mg)":       "pyridoxine_mg",
    "B12 (Cobalamin) (µg)":       "cobalamin_mcg",
    "Beta-carotene (µg)":         "beta_carotene_mcg",
    "Folate (µg)":                "folate_mcg",
    "Vitamin A (µg)":             "vitamin_a_mcg",
    "Vitamin C (mg)":             "vitamin_c_mg",
    # Vitamin D handled separately (IU → mcg)
    "Vitamin E (mg)":             "vitamin_e_mg",
    "Vitamin K (µg)":             "vitamin_k_mcg",
    "ALA (g)":                    "omega3_ala_g",
    "DHA (g)":                    "omega3_dha_g",
    "EPA (g)":                    "omega3_epa_g",
    "AA (g)":                     "omega6_aa_g",
    "LA (g)":                     "omega6_la_g",
    "Alcohol (g)":                "alcohol_g",
    "Caffeine (mg)":              "caffeine_mg",
    "Oxalate (mg)":               "oxalate_mg",
    "Phytate (mg)":               "phytate_mg",
    "Water (g)":                  "water_g",
    # Amino acids
    "Cystine (g)":                "cystine_g",
    "Histidine (g)":              "histidine_g",
    "Isoleucine (g)":             "isoleucine_g",
    "Leucine (g)":                "leucine_g",
    "Lysine (g)":                 "lysine_g",
    "Methionine (g)":             "methionine_g",
    "Phenylalanine (g)":          "phenylalanine_g",
    "Threonine (g)":              "threonine_g",
    "Tryptophan (g)":             "tryptophan_g",
    "Tyrosine (g)":               "tyrosine_g",
    "Valine (g)":                 "valine_g",
    # Skipped: Net Carbs (calculated), Starch (no field),
    #          Omega-3/Omega-6 totals (we keep subtypes individually)
}

IU_TO_MCG_VIT_D = 0.025   # 1 IU Vitamin D = 0.025 mcg


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_grams(amount_str: str):
    """Return gram equivalent of an amount string, or None if not parseable."""
    s = amount_str.strip()
    m = re.match(r'^([\d.]+)\s*g$', s, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.match(r'^([\d.]+)\s*oz$', s, re.IGNORECASE)
    if m:
        return round(float(m.group(1)) * 28.3495, 2)
    return None


def safe_float(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def row_to_nutrients(row: dict) -> dict:
    result = {}
    for csv_col, field in COLUMN_MAP.items():
        if csv_col in row:
            v = safe_float(row[csv_col])
            if v is not None:
                result[field] = v
    vit_d_iu = safe_float(row.get("Vitamin D (IU)", ""))
    if vit_d_iu is not None:
        result["vitamin_d_mcg"] = round(vit_d_iu * IU_TO_MCG_VIT_D, 4)
    return result


def scale_nutrients(nutrients: dict, from_g: float, to_g: float) -> dict:
    if from_g == 0:
        return nutrients
    factor = to_g / from_g
    return {k: round(v * factor, 6) for k, v in nutrients.items()}


def average_dicts(dicts: list) -> dict:
    totals = defaultdict(list)
    for d in dicts:
        for k, v in d.items():
            if v is not None:
                totals[k].append(v)
    return {k: round(sum(vs) / len(vs), 6) for k, vs in totals.items()}


# ── Build payloads ────────────────────────────────────────────────────────────

def build_payloads(rows: list) -> list:
    by_food = defaultdict(list)
    for row in rows:
        by_food[row["Food Name"].strip()].append(row)

    payloads = []
    for food_name, food_rows in by_food.items():
        gram_entries = []
        for row in food_rows:
            g = extract_grams(row["Amount"])
            if g and g > 0:
                gram_entries.append((g, row))

        if gram_entries:
            per_100g_list = [
                scale_nutrients(row_to_nutrients(row), from_g=g, to_g=100.0)
                for g, row in gram_entries
            ]
            averaged = average_dicts(per_100g_list)
            payload = {
                "name":             food_name,
                "source":           "personal",
                "serving_size_g":   100.0,
                "serving_size_desc": "100 g",
                **averaged,
            }
        else:
            first = food_rows[0]
            payload = {
                "name":             food_name,
                "source":           "personal",
                "serving_size_g":   None,
                "serving_size_desc": first["Amount"].strip(),
                **row_to_nutrients(first),
            }

        payload.setdefault("calories",  0.0)
        payload.setdefault("protein_g", 0.0)
        payload.setdefault("fat_g",     0.0)
        payload.setdefault("carbs_g",   0.0)
        payloads.append(payload)

    return payloads


# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path: str):
    req = urllib.request.Request(f"{API_URL}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_post(path: str, data: dict):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f"{API_URL}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def api_patch(path: str, data: dict):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(
        f"{API_URL}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="PATCH"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def get_existing_personal(existing_map: dict):
    """Return {name: id} for all personal-source foods in the DB."""
    try:
        items = api_get("/api/v1/foods/?source=personal")
        return {item["name"]: item["id"] for item in items}
    except Exception as e:
        print(f"  ⚠️  Could not fetch existing foods: {e}")
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit",     type=int)
    args = parser.parse_args()

    if not CSV_PATH.exists():
        print(f"❌ CSV not found: {CSV_PATH}")
        sys.exit(1)

    print(f"📂 Reading {CSV_PATH.name} …")
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"   {len(rows):,} diary rows")

    payloads = build_payloads(rows)
    if args.limit:
        payloads = payloads[:args.limit]

    gram_count = sum(1 for p in payloads if p.get("serving_size_g") == 100.0)
    print(f"   {len(payloads):,} unique foods  "
          f"({gram_count} normalised to 100g,  {len(payloads)-gram_count} stored by serving)")

    if args.dry_run:
        print("\n── DRY RUN — first 8 payloads ──────────────────────────────────")
        for p in payloads[:8]:
            print(f"  {p['name']!r:55s}  {p.get('serving_size_desc','?'):14s}"
                  f"  cal={p.get('calories',0):.0f}  P={p.get('protein_g',0):.1f}g"
                  f"  VitC={p.get('vitamin_c_mg','—')}")
        print(f"\n  → would import {len(payloads):,} foods to {API_URL}")
        return

    # ── Live run ──
    print(f"\n🌐 API: {API_URL}")
    try:
        health = api_get("/health")
        print(f"   ✅ Connected ({health.get('status', 'ok')})")
    except Exception as e:
        print(f"   ❌ Cannot reach API: {e}")
        print(f"      Set API_URL=https://<your-app>.up.railway.app")
        sys.exit(1)

    print("   Fetching existing personal foods …")
    existing = get_existing_personal({})
    print(f"   {len(existing):,} already in DB")

    created = skipped = updated = errors = 0
    t0 = time.time()

    for i, payload in enumerate(payloads, 1):
        name = payload["name"]

        if i % 100 == 0 or i == len(payloads):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed else 1
            eta  = (len(payloads) - i) / rate
            print(f"   [{i:4d}/{len(payloads)}]  "
                  f"✅ {created}  🔄 {updated}  ⏭ {skipped}  ❌ {errors}  "
                  f"({rate:.0f}/s, ETA {eta:.0f}s)")

        if name in existing:
            if args.overwrite:
                status, _ = api_patch(f"/api/v1/foods/{existing[name]}", payload)
                if status == 200:
                    updated += 1
                else:
                    errors += 1
                    print(f"   ❌ PATCH {name!r}: HTTP {status}")
            else:
                skipped += 1
            continue

        status, body = api_post("/api/v1/foods/", payload)
        if status in (200, 201):
            created += 1
            if isinstance(body, dict):
                existing[name] = body.get("id", "")
        else:
            errors += 1
            print(f"   ❌ {name!r}: HTTP {status} — {body}")

    elapsed = time.time() - t0
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Created : {created:,}")
    print(f"   Updated : {updated:,}")
    print(f"   Skipped : {skipped:,}  (use --overwrite to replace)")
    print(f"   Errors  : {errors:,}")


if __name__ == "__main__":
    main()
