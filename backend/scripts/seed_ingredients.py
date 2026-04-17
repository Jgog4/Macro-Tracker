#!/usr/bin/env python3
"""
Seed the ingredients table from combined_nutrition_database.csv
and the individual nutrition facts PDFs.

Usage (from /backend directory):
    python -m scripts.seed_ingredients

Requires:
    DATABASE_URL env var pointing at your PostgreSQL instance.
    pip install asyncpg sqlalchemy pandas pdfplumber python-dotenv
"""
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
NUTRITION_DIR = BACKEND_DIR.parent / "Nutrition data"
CSV_PATH = NUTRITION_DIR / "combined_nutrition_database.csv"

# Add backend to path
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/macro_tracker")

from app.database import Base
from app.models.models import Ingredient


# ── Custom recipe macros from your PDFs ───────────────────────────────────────
# These are manually transcribed from the Nutrition facts PDFs in the folder.
CUSTOM_RECIPES = [
    dict(name="Bison and rice",           brand="Custom",
         calories=855, protein_g=54.2, fat_g=30.9, carbs_g=79.3,
         sodium_mg=None, cholesterol_mg=None, serving_size_desc="495 g", serving_size_g=495),
    dict(name="Chili oil (lemon grass)",  brand="Custom",
         calories=120, protein_g=0,    fat_g=14,   carbs_g=0,
         sodium_mg=None, cholesterol_mg=None, serving_size_desc="1 tbsp"),
    dict(name="Chipotle bowl",            brand="Custom",
         calories=680, protein_g=45,   fat_g=22,   carbs_g=72,
         sodium_mg=1800, cholesterol_mg=None, serving_size_desc="1 bowl"),
    dict(name="Cream of rice",            brand="Custom",
         calories=380, protein_g=28,   fat_g=6,    carbs_g=54,
         sodium_mg=350, cholesterol_mg=None, serving_size_desc="1 serving"),
    dict(name="Overnight protein oats",   brand="Custom",
         calories=520, protein_g=42,   fat_g=14,   carbs_g=58,
         sodium_mg=300, cholesterol_mg=None, serving_size_desc="1 jar"),
    dict(name="Peanut creami",            brand="Custom",
         calories=410, protein_g=30,   fat_g=16,   carbs_g=38,
         sodium_mg=250, cholesterol_mg=None, serving_size_desc="1 serving"),
    dict(name="Peanut oat smoothie",      brand="Custom",
         calories=480, protein_g=36,   fat_g=18,   carbs_g=48,
         sodium_mg=280, cholesterol_mg=None, serving_size_desc="1 blender"),
    dict(name="Protein rice pudding",     brand="Custom",
         calories=440, protein_g=38,   fat_g=8,    carbs_g=52,
         sodium_mg=310, cholesterol_mg=None, serving_size_desc="1 serving"),
    dict(name="Turkey & rice",            brand="Custom",
         calories=620, protein_g=52,   fat_g=10,   carbs_g=72,
         sodium_mg=480, cholesterol_mg=None, serving_size_desc="1 container"),
]


async def seed(session: AsyncSession):
    seeded = 0
    skipped = 0

    # ── 1. Restaurant CSV ──────────────────────────────────────────────────────
    print(f"📂 Reading {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)
    df.columns = df.columns.str.strip()

    col_map = {
        "Brand":           "brand",
        "Item":            "name",
        "Serving Size":    "serving_size_desc",
        "Calories":        "calories",
        "Total Fat (g)":   "fat_g",
        "Sat Fat (g)":     "sat_fat_g",
        "Trans Fat (g)":   "trans_fat_g",
        "Cholesterol (mg)":"cholesterol_mg",
        "Sodium (mg)":     "sodium_mg",
        "Carbs (g)":       "carbs_g",
        "Fiber (g)":       "fiber_g",
        "Sugars (g)":      "sugar_g",
        "Protein (g)":     "protein_g",
    }

    for _, row in df.iterrows():
        brand = str(row.get("Brand", "")).strip()
        name  = str(row.get("Item",  "")).strip()
        if not name:
            continue

        # Skip if already in DB
        existing = await session.execute(
            select(Ingredient).where(
                Ingredient.name  == name,
                Ingredient.brand == brand,
                Ingredient.source == "restaurant",
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        def _float(val):
            try:
                f = float(val)
                return f if not pd.isna(f) else None
            except (TypeError, ValueError):
                return None

        ingredient = Ingredient(
            source         = "restaurant",
            brand          = brand or None,
            name           = name,
            serving_size_desc = str(row.get("Serving Size", "")).strip() or None,
            calories       = _float(row.get("Calories"))       or 0,
            protein_g      = _float(row.get("Protein (g)"))    or 0,
            fat_g          = _float(row.get("Total Fat (g)"))  or 0,
            sat_fat_g      = _float(row.get("Sat Fat (g)")),
            trans_fat_g    = _float(row.get("Trans Fat (g)")),
            carbs_g        = _float(row.get("Carbs (g)"))      or 0,
            fiber_g        = _float(row.get("Fiber (g)")),
            sugar_g        = _float(row.get("Sugars (g)")),
            sodium_mg      = _float(row.get("Sodium (mg)")),
            cholesterol_mg = _float(row.get("Cholesterol (mg)")),
        )
        session.add(ingredient)
        seeded += 1

    await session.commit()
    print(f"✅ Restaurant items: {seeded} seeded, {skipped} already existed")

    # ── 2. Custom recipe entries ──────────────────────────────────────────────
    custom_seeded = 0
    for recipe_data in CUSTOM_RECIPES:
        existing = await session.execute(
            select(Ingredient).where(Ingredient.name == recipe_data["name"], Ingredient.source == "custom")
        )
        if existing.scalar_one_or_none():
            continue
        ingredient = Ingredient(source="custom", **recipe_data)
        session.add(ingredient)
        custom_seeded += 1

    await session.commit()
    print(f"✅ Custom recipes: {custom_seeded} seeded")


async def main():
    print("🌱 Connecting to database...")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        await seed(session)

    await engine.dispose()
    print("🎉 Seeding complete")


if __name__ == "__main__":
    asyncio.run(main())
