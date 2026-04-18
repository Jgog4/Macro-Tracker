#!/usr/bin/env python3
"""
Import your personal food history into the ingredients table.

Reads Nutrition data/personal_foods.csv (a "Servings" export from your
nutrition tracking history). Every food recorded with a weight in grams
(or oz / mL) gets normalized to per-100 g values and inserted as
source="personal". If the item already exists it is skipped.

Usage (from /backend directory):
    python -m scripts.seed_personal_foods

Requires:
    DATABASE_URL env var pointing at your PostgreSQL instance.
    pip install asyncpg sqlalchemy python-dotenv
"""
import asyncio
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
BACKEND_DIR  = SCRIPT_DIR.parent
NUTRITION_DIR = BACKEND_DIR.parent / "Nutrition data"
CSV_PATH     = NUTRITION_DIR / "personal_foods.csv"

sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/macro_tracker")
# Railway injects postgresql:// — convert to asyncpg driver
DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

from app.database import Base
from app.models.models import Ingredient


# ── Amount → grams conversion ─────────────────────────────────────────────────
def parse_grams(amount_str: str) -> float | None:
    """
    Convert a Cronometer amount string to grams.
    Handles: "40.00 g", "2.50 oz", "250.00 mL", "8.00 fl oz"
    Returns None for unit-less entries (scoops, pieces, etc.)
    """
    s = amount_str.strip()

    # Plain grams: "40.00 g"
    m = re.match(r"^([\d.]+)\s*g\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1))

    # Ounces: "2.00 oz"
    m = re.match(r"^([\d.]+)\s*oz\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 28.3495

    # Millilitres: "250.00 mL"  (density ≈ 1 g/mL — good enough for most liquids)
    m = re.match(r"^([\d.]+)\s*m[lL]\s*$", s)
    if m:
        return float(m.group(1))

    # Fluid ounces: "8.00 fl oz"
    m = re.match(r"^([\d.]+)\s*fl\.?\s*oz\.?\s*$", s, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 29.5735

    return None


# ── Safe numeric parse ────────────────────────────────────────────────────────
def _f(val) -> float | None:
    """Convert string to float; return None on blank or non-numeric."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        v = float(s)
        return v if v == v else None  # reject NaN
    except ValueError:
        return None


# ── Load and aggregate CSV ────────────────────────────────────────────────────
def load_personal_foods(csv_path: Path) -> list[dict]:
    """
    Parse cronometer_servings.csv and return a list of dicts, one per unique
    food name.  All macro values are normalised to per-100 g.  The default
    serving size is set to the mode (most-common) gram amount the user logged.
    """
    by_name: dict[str, list[dict]] = defaultdict(list)

    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name   = row["Food Name"].strip()
            grams  = parse_grams(row["Amount"])
            if not grams or grams < 0.5:
                continue

            by_name[name].append({
                "grams":         grams,
                "amount_str":    row["Amount"].strip(),
                "calories":      _f(row["Energy (kcal)"]),
                "protein_g":     _f(row["Protein (g)"]),
                "fat_g":         _f(row["Fat (g)"]),
                "carbs_g":       _f(row["Carbs (g)"]),
                "fiber_g":       _f(row["Fiber (g)"]),
                "sugar_g":       _f(row["Sugars (g)"]),
                "sodium_mg":     _f(row["Sodium (mg)"]),
                "cholesterol_mg":_f(row["Cholesterol (mg)"]),
                "sat_fat_g":     _f(row["Saturated (g)"]),
                "trans_fat_g":   _f(row["Trans-Fats (g)"]),
            })

    results = []
    for name, entries in by_name.items():
        # Weighted average of per-gram values (weight = gram amount)
        def w_avg(key: str) -> float | None:
            pairs = [(e[key] / e["grams"], e["grams"])
                     for e in entries
                     if e[key] is not None and e["grams"] > 0]
            if not pairs:
                return None
            total_w = sum(w for _, w in pairs)
            return sum(v * w for v, w in pairs) / total_w

        # Most-common gram amount becomes the default serving size
        gram_counts = Counter(round(e["grams"]) for e in entries)
        typical_g   = gram_counts.most_common(1)[0][0]

        # Per-100 g macros
        def per100(key: str) -> float | None:
            v = w_avg(key)
            return round(v * 100, 4) if v is not None else None

        cal   = per100("calories")
        prot  = per100("protein_g")
        fat   = per100("fat_g")
        carbs = per100("carbs_g")

        # Skip entries with no usable macro data
        if cal is None and prot is None and fat is None and carbs is None:
            continue

        results.append({
            "name":            name,
            "source":          "personal",
            "serving_size_g":  float(typical_g),
            "serving_size_desc": f"{typical_g} g",
            "calories":        cal   or 0.0,
            "protein_g":       prot  or 0.0,
            "fat_g":           fat   or 0.0,
            "carbs_g":         carbs or 0.0,
            "fiber_g":         per100("fiber_g"),
            "sugar_g":         per100("sugar_g"),
            "sodium_mg":       per100("sodium_mg"),
            "cholesterol_mg":  per100("cholesterol_mg"),
            "sat_fat_g":       per100("sat_fat_g"),
            "trans_fat_g":     per100("trans_fat_g"),
        })

    return results


# ── Database seeding ──────────────────────────────────────────────────────────
async def seed(session: AsyncSession):
    print(f"📂 Reading {CSV_PATH}")
    foods = load_personal_foods(CSV_PATH)
    print(f"   → {len(foods)} unique foods with gram-based amounts")

    seeded = 0
    skipped = 0

    for food in foods:
        # Idempotent: skip if already in DB with same name + personal source
        existing = await session.execute(
            select(Ingredient).where(
                Ingredient.name   == food["name"],
                Ingredient.source == "personal",
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        ingredient = Ingredient(**food)
        session.add(ingredient)
        seeded += 1

        if seeded % 100 == 0:
            await session.commit()
            print(f"   … {seeded} seeded so far")

    await session.commit()
    print(f"✅ Personal foods: {seeded} seeded, {skipped} already existed")


async def main():
    if not CSV_PATH.exists():
        print(f"❌ CSV not found at {CSV_PATH}")
        print("   Place your Cronometer 'Servings' export there and try again.")
        sys.exit(1)

    print("🌱 Connecting to database...")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        await seed(session)

    await engine.dispose()
    print("🎉 Done — your personal food library is ready")


if __name__ == "__main__":
    asyncio.run(main())
