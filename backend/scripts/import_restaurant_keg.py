"""
Import The Keg's published nutrition guide into mt_ingredients.

Source: https://files.thekeg.com/nutritional-guide.pdf — a PDF the restaurant
publishes for customers. Far more stable than scraping a site, and unambiguously
meant to be read.

Two details make this harder than "extract the text":

  * **Columns must be read by position.** Flat text extraction silently drops
    four of the fifteen columns — Total Fat, Cholesterol, Carbs and Calcium —
    because of how the table is laid out in the PDF. Reading words with their
    x-coordinates and assigning each to the nearest column header recovers all
    fifteen. A row parsed the naive way looks complete and is wrong.
  * **The guide is bilingual.** Pages 1-9 are English, 10-18 repeat everything
    in French. Only the English half is imported.

Every row is checked against the energy equation (4·protein + 4·carbs +
9·fat ≈ calories). Rows that disagree by more than 15% are a sign the PDF's
text layer garbled that line, and are reported and skipped rather than
imported — "Grilled Jumbo Shrimp" comes through as 150 kcal with 61 g of fat.

The four %DV micronutrient columns are deliberately NOT imported: the vitamin C
column reaches 402% of daily value on restaurant dishes, which is not credible,
and suspect micronutrients are worse than absent ones.

    python scripts/import_restaurant_keg.py [--dry-run] [--pdf PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pdfplumber
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Ingredient

BRAND = "The Keg"
PDF_URL = "https://files.thekeg.com/nutritional-guide.pdf"
ENGLISH_PAGES = 9          # pages 10-18 are the French translation
ENERGY_TOLERANCE = 0.15
# A percentage alone is unfair to small items: "Side of Peppercorn" is 110 kcal
# and 23 kcal of rounding across four columns trips a 15% test. Allow whichever
# is larger, so the check still bites where it matters (big mis-columned rows).
ENERGY_FLOOR_KCAL = 35

# Column x-positions read off the table header, mapped to our columns.
# `None` means the column is deliberately not imported.
COLUMNS: list[tuple[int, str | None]] = [
    (168, "serving_size_g"),
    (216, "calories"),
    (256, "fat_g"),
    (296, "sat_fat_g"),
    (336, "trans_fat_g"),
    (384, "cholesterol_mg"),
    (408, "sodium_mg"),
    (448, "carbs_g"),
    (488, "fiber_g"),
    (528, "sugar_g"),
    (568, "protein_g"),
    (608, None),           # Vit A  %DV — see module docstring
    (648, None),           # Vit C  %DV
    (688, None),           # Calcium %DV
    (728, None),           # Iron   %DV
]
NAME_MAX_X = 165           # text left of this is the item name
COL_TOLERANCE = 26         # how far a value may sit from its header
NUMERIC = re.compile(r"^(?:[\d,]+(?:\.\d+)?|N/A)$")

# Lines that are headings or legal text, not menu items.
SKIP_NAME = re.compile(
    r"^(DINNER|LUNCH|KIDS|DESSERT|APPETIZERS|SALADS|ACCOMPANIMENTS|CASUAL|"
    r"SHAREABLE|KEG CLASSICS|ADD TO|Serving|Nutritional|Some Keg|Only standard|"
    r"DAILY|calories per day|milligrams|preparation|laboratory|The actual)",
    re.I,
)


def column_for(x: float) -> str | None | bool:
    """Which column does a value at this x belong to? False = no column."""
    x0, name = min(COLUMNS, key=lambda c: abs(c[0] - x))
    return name if abs(x0 - x) < COL_TOLERANCE else False


def to_float(text: str | None) -> float | None:
    if text in (None, "", "N/A"):
        return None
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def parse_pdf(path: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Returns (rows, rejected) — rejected carries a reason for reporting."""
    rows: list[dict] = []
    rejected: list[tuple[str, str]] = []
    seen: set[str] = set()

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:ENGLISH_PAGES]:
            lines: dict[int, list] = {}
            for word in page.extract_words():
                lines.setdefault(round(word["top"] / 3) * 3, []).append(word)

            for _, words in sorted(lines.items()):
                words = sorted(words, key=lambda w: w["x0"])
                name = " ".join(w["text"] for w in words if w["x0"] < NAME_MAX_X).strip()
                if not name or SKIP_NAME.match(name):
                    continue

                values: dict[str, str] = {}
                for w in words:
                    if w["x0"] < NAME_MAX_X or not NUMERIC.match(w["text"]):
                        continue
                    col = column_for(w["x0"])
                    if col and col not in values:      # first wins; None/False skipped
                        values[col] = w["text"]

                if "calories" not in values or "serving_size_g" not in values:
                    continue

                key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
                if key in seen:
                    continue

                data = {k: to_float(v) for k, v in values.items()}
                kcal = data.get("calories")
                if not kcal or kcal <= 0:
                    rejected.append((name, "no calories"))
                    continue

                # The energy equation is the only independent check available on
                # a PDF's text layer, and it catches exactly the failure mode
                # that matters: a value landing in the wrong column.
                p, c, f = data.get("protein_g"), data.get("carbs_g"), data.get("fat_g")
                if None not in (p, c, f):
                    implied = 4 * p + 4 * c + 9 * f
                    allowed = max(kcal * ENERGY_TOLERANCE, ENERGY_FLOOR_KCAL)
                    if abs(implied - kcal) > allowed:
                        rejected.append(
                            (name, f"energy mismatch: {implied:.0f} vs {kcal:.0f} kcal")
                        )
                        continue

                seen.add(key)
                data["name"] = name
                rows.append(data)
    return rows, rejected


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="", help="use a local PDF instead of downloading")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = args.pdf
    if not path:
        path = "/tmp/keg-nutritional-guide.pdf"
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(PDF_URL, headers={"User-Agent": "MacroTrackerPersonal/1.0"})
            r.raise_for_status()
            with open(path, "wb") as fh:
                fh.write(r.content)
        print(f"downloaded {len(r.content):,} bytes")

    rows, rejected = parse_pdf(path)
    print(f"parsed {len(rows)} items · rejected {len(rejected)}")

    engine = create_async_engine(os.environ["DBURL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    created = updated = 0

    async with Session() as db:
        for row in rows:
            name = row.pop("name")
            existing = (await db.execute(
                select(Ingredient).where(Ingredient.brand == BRAND, Ingredient.name == name)
            )).scalar_one_or_none()
            if existing is None:
                existing = Ingredient(source="restaurant", brand=BRAND, name=name)
                db.add(existing)
                created += 1
            else:
                updated += 1
            for col, val in row.items():
                if val is not None:
                    setattr(existing, col, val)
            # The guide gives a real gram serving, so values are per serving and
            # the app's base_g = serving_size_g rule scales them correctly.
            existing.serving_size_desc = "1 serving"

        if args.dry_run:
            await db.rollback()
            print("(dry run — nothing written)")
        else:
            await db.commit()
            print(f"DONE  created={created} updated={updated}")

    if rejected:
        print(f"\nrejected {len(rejected)} rows (not imported):")
        for name, why in rejected[:15]:
            print(f"   {name[:44]:<46} {why}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
