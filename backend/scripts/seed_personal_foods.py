#!/usr/bin/env python3
"""
Import your personal food history into the mt_ingredients table.

Reads Nutrition data/personal_foods.csv. Every food recorded with a weight
in grams (or oz / mL) gets normalized to per-100 g values and inserted as
source='personal'. Already-existing items are skipped.

Usage (from /backend directory):
    python3 -m scripts.seed_personal_foods

Requires:
    DATABASE_URL env var (injected automatically by: railway run python3 ...)
    pip3 install asyncpg python-dotenv
"""
import asyncio
import csv
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).parent
BACKEND_DIR   = SCRIPT_DIR.parent
NUTRITION_DIR = BACKEND_DIR.parent / "Nutrition data"
CSV_PATH      = NUTRITION_DIR / "personal_foods.csv"

# Load .env if present (for local runs without railway run)
env_file = BACKEND_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set. Run with: railway run python3 -m scripts.seed_personal_foods")
    sys.exit(1)

# asyncpg needs postgresql:// not postgresql+asyncpg://
DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)

try:
    import asyncpg
except ImportError:
    print("❌ asyncpg not installed. Run: pip3 install asyncpg")
    sys.exit(1)


# ── Amount → grams ────────────────────────────────────────────────────────────
def parse_grams(amount_str):
    s = amount_str.strip()
    m = re.match(r"^([\d.]+)\s*g\s*$", s, re.IGNORECASE)
    if m: return float(m.group(1))
    m = re.match(r"^([\d.]+)\s*oz\s*$", s, re.IGNORECASE)
    if m: return float(m.group(1)) * 28.3495
    m = re.match(r"^([\d.]+)\s*m[lL]\s*$", s)
    if m: return float(m.group(1))
    m = re.match(r"^([\d.]+)\s*fl\.?\s*oz\.?\s*$", s, re.IGNORECASE)
    if m: return float(m.group(1)) * 29.5735
    return None


def _f(val):
    if val is None: return None
    s = str(val).strip()
    if not s: return None
    try:
        v = float(s)
        return v if v == v else None
    except ValueError:
        return None


# ── Load & aggregate CSV ──────────────────────────────────────────────────────
def load_personal_foods(csv_path):
    by_name = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name  = row["Food Name"].strip()
            grams = parse_grams(row["Amount"])
            if not grams or grams < 0.5:
                continue
            by_name[name].append({
                "grams":          grams,
                "amount_str":     row["Amount"].strip(),
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
            })

    results = []
    for name, entries in by_name.items():
        def w_avg(key):
            pairs = [(e[key] / e["grams"], e["grams"])
                     for e in entries
                     if e[key] is not None and e["grams"] > 0]
            if not pairs: return None
            total_w = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / total_w

        def per100(key):
            v = w_avg(key)
            return round(v * 100, 4) if v is not None else None

        cal   = per100("calories")
        prot  = per100("protein_g")
        fat   = per100("fat_g")
        carbs = per100("carbs_g")
        if cal is None and prot is None and fat is None and carbs is None:
            continue

        gram_counts = Counter(round(e["grams"]) for e in entries)
        typical_g   = float(gram_counts.most_common(1)[0][0])

        # Store macros AT the typical serving size (not per-100g).
        # _scale_macros uses: ratio = qty_g / serving_size_g
        # so macros must equal "nutrients at serving_size_g grams".
        def at_serving(key):
            v = w_avg(key)          # per-gram value
            return round(v * typical_g, 4) if v is not None else None

        results.append({
            "id":               str(uuid.uuid4()),
            "name":             name,
            "source":           "personal",
            "serving_size_g":   typical_g,
            "serving_size_desc": f"{int(typical_g)} g",
            "calories":         at_serving("calories")       or 0.0,
            "protein_g":        at_serving("protein_g")      or 0.0,
            "fat_g":            at_serving("fat_g")          or 0.0,
            "carbs_g":          at_serving("carbs_g")        or 0.0,
            "fiber_g":          at_serving("fiber_g"),
            "sugar_g":          at_serving("sugar_g"),
            "sodium_mg":        at_serving("sodium_mg"),
            "cholesterol_mg":   at_serving("cholesterol_mg"),
            "sat_fat_g":        at_serving("sat_fat_g"),
            "trans_fat_g":      at_serving("trans_fat_g"),
        })
    return results


# ── Seed database ─────────────────────────────────────────────────────────────
async def main():
    if not CSV_PATH.exists():
        print(f"❌ CSV not found at {CSV_PATH}")
        sys.exit(1)

    print(f"📂 Reading {CSV_PATH}")
    foods = load_personal_foods(CSV_PATH)
    print(f"   → {len(foods)} unique foods with gram-based amounts")

    print("🌱 Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)

    seeded = skipped = 0
    try:
        for food in foods:
            # Skip if already present
            existing = await conn.fetchval(
                "SELECT id FROM mt_ingredients WHERE name=$1 AND source='personal'",
                food["name"]
            )
            if existing:
                skipped += 1
                continue

            await conn.execute("""
                INSERT INTO mt_ingredients
                  (id, source, name, serving_size_g, serving_size_desc,
                   calories, protein_g, fat_g, carbs_g,
                   fiber_g, sugar_g, sodium_mg, cholesterol_mg,
                   sat_fat_g, trans_fat_g,
                   created_at, updated_at)
                VALUES
                  ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,NOW(),NOW())
            """,
                food["id"], food["source"], food["name"],
                food["serving_size_g"], food["serving_size_desc"],
                food["calories"], food["protein_g"], food["fat_g"], food["carbs_g"],
                food["fiber_g"], food["sugar_g"], food["sodium_mg"], food["cholesterol_mg"],
                food["sat_fat_g"], food["trans_fat_g"],
            )
            seeded += 1
            if seeded % 100 == 0:
                print(f"   … {seeded} inserted so far")

    finally:
        await conn.close()

    print(f"✅ Personal foods: {seeded} seeded, {skipped} already existed")
    print("🎉 Done — your personal food library is ready")


if __name__ == "__main__":
    asyncio.run(main())
