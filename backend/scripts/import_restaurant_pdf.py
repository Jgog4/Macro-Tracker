"""
Import a restaurant's published nutrition-guide PDF into mt_ingredients.

One parser, one column map per chain. Everything chain-specific lives in
BRANDS; extraction and validation below are shared.

Three things make this harder than "extract the text":

  * **Columns must be read by position.** Flat text extraction silently drops
    four of The Keg's fifteen columns — Total Fat, Cholesterol, Carbs and
    Calcium — because of how that table is laid out. A row parsed the naive way
    looks complete and is wrong. Each word is assigned to the nearest column
    header by x-coordinate instead.
  * **Rows must be grouped by proximity, not by rounding.** A name and its
    numbers sit on slightly different baselines (Panera: 185.24 vs 187.23).
    Bucketing with round(top / n) splits any pair that straddles a bucket
    boundary, which silently drops menu items — it cost ~70% of Panera's guide.
    Words are clustered into rows by gap instead: within a row the offset is
    under 2.1pt everywhere, between rows it is at least 5.3pt.
  * **Some guides list alcohol.** Ethanol carries 7 kcal/g and is not one of
    the printed macros, so a cocktail's calories legitimately exceed 4P+4C+9F.
    Those rows are found by section heading, not by guessing at brand names,
    and the shortfall is recorded as alcohol_g.

Every other row is checked against the energy equation (4·protein + 4·carbs +
9·fat ≈ calories) — the only independent check a PDF's text layer allows, and
it catches exactly the failure that matters: a value landing in the wrong
column. Rows that fail are reported and skipped rather than imported.

The check accepts either total or net carbohydrate, because some chains cost
their calories on net carbs: Panera's Black Bean Soup is 41g carbs of which
18g is fibre, and 4P + 4(41-18) + 9F = 142 against a published 140. Demanding
total carbs would throw away every high-fibre item on the menu.

    python3.13 scripts/import_restaurant_pdf.py <brand> [--pdf PATH] [--dry-run]
    python3.13 scripts/import_restaurant_pdf.py --list

Needs pdfplumber, which is deliberately NOT in requirements.txt — this is a
local one-off tool and Railway should not build it.
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

# `None` in a column map means "this column exists but is not imported".
BRANDS: dict[str, dict] = {
    "keg": {
        "brand": "The Keg",
        "url": "https://files.thekeg.com/nutritional-guide.pdf",
        "pages": 9,              # pages 10-18 repeat everything in French
        "name_max_x": 165,
        "serving_is_grams": True,
        "columns": [
            (168, "serving_size_g"), (216, "calories"), (256, "fat_g"),
            (296, "sat_fat_g"), (336, "trans_fat_g"), (384, "cholesterol_mg"),
            (408, "sodium_mg"), (448, "carbs_g"), (488, "fiber_g"),
            (528, "sugar_g"), (568, "protein_g"),
            # Vit A / Vit C / Calcium / Iron are published as %DV and are not
            # imported: the vitamin C column reaches 402% DV on a restaurant
            # dish, which is not credible, and suspect micros are worse than
            # absent ones.
            (608, None), (648, None), (688, None), (728, None),
        ],
    },
    "pfchangs": {
        "brand": "P.F. Chang's",
        "url": "https://www.pfchangs.com/docs/default-source/pdf/pfc-national-menu-nutrition-june-2026.pdf",
        "name_max_x": 200,
        # The first column counts servings per dish, not grams. It reads 1 on
        # all 262 rows, so the printed figures are per listed item.
        "serving_is_grams": False,
        "columns": [
            (253, None), (287, "calories"), (330, None),   # servings, cals-from-fat
            (375, "fat_g"), (414, "sat_fat_g"), (446, "trans_fat_g"),
            (481, "cholesterol_mg"), (525, "sodium_mg"), (578, "carbs_g"),
            (623, "fiber_g"), (664, "sugar_g"), (707, "protein_g"),
        ],
    },
    "tgifridays": {
        "brand": "TGI Fridays",
        "url": ("https://tgifridays.com/wp-content/uploads/2026/02/"
                "TGI-Fridays-SYSTEM-ANI-Document-Q1-2026-Rollout-post-02.17.2027v1.pdf"),
        "name_max_x": 200,
        "serving_is_grams": False,
        # The guide opens with drink sections (THE POWER POURS, CLASSIC
        # COCKTAILS, LONG ISLAND TEAS, MARGARITAS, BEERS) and this heading ends
        # them. Everything before it is alcoholic; everything after is not.
        "alcohol_until": re.compile(r"NON-?ALCOHOLIC", re.I),
        "columns": [
            (285, "calories"), (303, "fat_g"), (318, "sat_fat_g"),
            (332, "trans_fat_g"), (346, "cholesterol_mg"), (359, "sodium_mg"),
            (375, "carbs_g"), (388, "fiber_g"), (403, "sugar_g"),
            (418, "protein_g"),
        ],
    },
    "panera": {
        "brand": "Panera Bread",
        "url": "https://www.panerabread.com/content/dam/panerabread/documents/c6-26-nutrition-guide.pdf",
        "name_max_x": 235,
        # Serving size is descriptive text ("1 Bagel"), not a weight.
        "serving_is_grams": False,
        # Long item names wrap onto a second line, which arrives as a row with
        # no numbers. Join it back on rather than truncating the name.
        "wrapped_names": True,
        "columns": [
            (258, None), (337, "calories"), (371, None),   # serving text, cals-from-fat
            (405, "fat_g"), (437, "sat_fat_g"), (470, "trans_fat_g"),
            (500, "cholesterol_mg"), (531, "sodium_mg"), (565, "carbs_g"),
            (599, "fiber_g"), (631, "sugar_g"), (662, "protein_g"),
            (707, "caffeine_mg"),
        ],
    },
}

COL_TOLERANCE = 14.0    # how far a value may sit from its column's x
LINE_TOLERANCE = 4.0    # vertical gap that still counts as the same row
WRAP_MAX_GAP = 14.0     # a continuation line is never further than one row away
MIN_VALUES = 5          # fewer columns than this is a heading, not an item
ENERGY_TOLERANCE = 0.15
# A percentage alone is unfair to small items: a 110 kcal side with 23 kcal of
# rounding spread over four columns would trip a flat 15% test. Allow whichever
# is larger, so the check still bites where it matters — big mis-columned rows.
ENERGY_FLOOR_KCAL = 35
KCAL_PER_G_ALCOHOL = 7.0
# A 750ml bottle of wine at 13% ABV is 77g of ethanol and appears on TGI's menu
# as a single line item, so the guard has to sit above that. It exists to catch
# a mis-parse, not to judge a drink.
MAX_PLAUSIBLE_ALCOHOL_G = 100.0

NUMERIC = re.compile(r"^(?:[\d,]+(?:\.\d+)?|N/A|<\d+)$")

# Legal boilerplate and column legends that would otherwise look like items.
SKIP_NAME = re.compile(
    r"^(Serving|Nutrition|Nutritional|Some |Only standard|DAILY|calories|"
    r"milligrams|preparation|laboratory|The actual|Effective|Revised|Cal\b|"
    r"Sat\b|Carbs\b|To our guests|Regular kitchen|\d{1,2}/\d{1,2}/\d{4}|\W*$)",
    re.I,
)


def to_float(text: str | None) -> float | None:
    if text in (None, "", "N/A"):
        return None
    try:
        return float(str(text).replace(",", "").lstrip("<"))
    except ValueError:
        return None


def cluster_rows(page) -> list[list[dict]]:
    """Group a page's words into rows by vertical proximity (see docstring)."""
    words = sorted(page.extract_words(), key=lambda w: w["top"])
    rows: list[list[dict]] = []
    for w in words:
        if rows and w["top"] - rows[-1][0]["top"] <= LINE_TOLERANCE:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def parse_pdf(path: str, cfg: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    columns = cfg["columns"]
    name_max_x = cfg["name_max_x"]
    alcohol_until = cfg.get("alcohol_until")
    rows: list[dict] = []
    rejected: list[tuple[str, str]] = []
    seen: set[str] = set()
    # TGI's guide leads with its bar menu; every other guide is food-only.
    in_alcohol = alcohol_until is not None

    def column_for(x: float):
        x0, col = min(columns, key=lambda c: abs(c[0] - x))
        return col if abs(x0 - x) < COL_TOLERANCE else False

    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[: cfg["pages"]] if cfg.get("pages") else pdf.pages
        for page in pages:
            # Read the page into flat line records first; joining wrapped names
            # needs to look at a line's neighbours.
            lines = []
            for words in cluster_rows(page):
                name = " ".join(w["text"] for w in words if w["x0"] < name_max_x)
                values: dict[str, str] = {}
                for w in words:
                    if w["x0"] < name_max_x or not NUMERIC.match(w["text"]):
                        continue
                    col = column_for(w["x0"])
                    if col and col not in values:   # first wins; None/False skipped
                        values[col] = w["text"]
                lines.append({
                    "name": re.sub(r"\s+", " ", name).strip(" .*\u2020\u2021"),
                    "values": values,
                    "top": words[0]["top"],
                    "bottom": max(w["bottom"] for w in words),
                })

            def is_wrap(idx: int) -> bool:
                """A name continuation: text, no figures, and not a heading."""
                if not (0 <= idx < len(lines)):
                    return False
                ln = lines[idx]
                return bool(
                    cfg.get("wrapped_names") and ln["name"]
                    and len(ln["values"]) < MIN_VALUES
                    and not SKIP_NAME.match(ln["name"])
                    and ln["name"] != ln["name"].upper()   # headings are all-caps
                )

            consumed: set[int] = set()
            for i, ln in enumerate(lines):
                name, values = ln["name"], ln["values"]

                if len(values) < MIN_VALUES:
                    if name and alcohol_until and alcohol_until.search(name):
                        in_alcohol = False
                    continue

                # Panera wraps long names around the figures: the head sits on
                # the line above and the tail on the line below. Only take a
                # tail when a head was found, so an item that simply precedes a
                # wrapped one does not swallow its first line.
                took_prefix = False
                if is_wrap(i - 1) and (i - 1) not in consumed \
                        and ln["top"] - lines[i - 1]["bottom"] <= WRAP_MAX_GAP:
                    name = f"{lines[i - 1]['name']} {name}".strip()
                    consumed.add(i - 1)
                    took_prefix = True
                if took_prefix and is_wrap(i + 1) \
                        and lines[i + 1]["top"] - ln["bottom"] <= WRAP_MAX_GAP:
                    name = f"{name} {lines[i + 1]['name']}".strip()
                    consumed.add(i + 1)

                if len(name) < 3 or SKIP_NAME.match(name):
                    continue

                data = {k: to_float(v) for k, v in values.items()}
                kcal = data.get("calories")
                if not kcal or kcal <= 0:
                    continue

                key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
                if key in seen:
                    continue

                p, c, f = data.get("protein_g"), data.get("carbs_g"), data.get("fat_g")
                if None not in (p, c, f):
                    implied = 4 * p + 4 * c + 9 * f
                    # Net-carb costing: see module docstring.
                    implied_net = implied - 4 * min(data.get("fiber_g") or 0.0, c)
                    allowed = max(kcal * ENERGY_TOLERANCE, ENERGY_FLOOR_KCAL)

                    if in_alcohol:
                        # Ethanol is not a printed macro, so the shortfall is
                        # what the alcohol accounts for. Record it rather than
                        # discarding a real menu item. The total-carb figure is
                        # used so the derived alcohol is the smaller estimate.
                        alcohol = (kcal - implied) / KCAL_PER_G_ALCOHOL
                        if alcohol > MAX_PLAUSIBLE_ALCOHOL_G:
                            rejected.append((name, f"implies {alcohol:.0f}g alcohol - suspect parse"))
                            continue
                        if implied_net - kcal > allowed:
                            # Macros exceeding the calories is a real error;
                            # alcohol can only ever add.
                            rejected.append((name, f"energy mismatch: {implied:.0f} vs {kcal:.0f} kcal"))
                            continue
                        if alcohol > 0.5:
                            data["alcohol_g"] = round(alcohol, 1)
                    elif min(abs(implied - kcal), abs(implied_net - kcal)) > allowed:
                        rejected.append((name, f"energy mismatch: {implied:.0f} vs {kcal:.0f} kcal"))
                        continue

                seen.add(key)
                data["name"] = name
                rows.append(data)

    if alcohol_until and in_alcohol:
        # The marker moved or the layout changed; every drink would be treated
        # as alcoholic. Better to stop than to write derived alcohol onto food.
        raise SystemExit("alcohol section end-marker not found - check the column map")
    return rows, rejected


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", nargs="?", help=f"one of: {', '.join(BRANDS)}")
    ap.add_argument("--pdf", default="", help="local PDF instead of downloading")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list or not args.brand:
        for key, cfg in BRANDS.items():
            print(f"  {key:<12} {cfg['brand']}")
        return
    if args.brand not in BRANDS:
        sys.exit(f"unknown brand {args.brand!r}; try --list")

    cfg = BRANDS[args.brand]
    path = args.pdf
    if not path:
        path = f"/tmp/{args.brand}-nutrition.pdf"
        with httpx.Client(timeout=90.0, follow_redirects=True) as client:
            r = client.get(cfg["url"], headers={"User-Agent": "MacroTrackerPersonal/1.0"})
            r.raise_for_status()
            with open(path, "wb") as fh:
                fh.write(r.content)
        print(f"downloaded {len(r.content):,} bytes")

    rows, rejected = parse_pdf(path, cfg)
    alcohol_rows = sum(1 for r in rows if r.get("alcohol_g"))
    print(f"{cfg['brand']}: parsed {len(rows)} items "
          f"({alcohol_rows} with alcohol) · rejected {len(rejected)}")

    engine = create_async_engine(os.environ["DBURL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)
    created = updated = 0

    async with Session() as db:
        # One query, not one per row: these guides run to 500+ items and the
        # import is normally run from a laptop over the public proxy, where a
        # round trip per row turns a few seconds into several minutes.
        by_name = {
            ing.name: ing
            for ing in (await db.execute(select(Ingredient).where(
                Ingredient.brand == cfg["brand"]))).scalars()
        }

        for row in rows:
            name = row.pop("name")
            existing = by_name.get(name)
            if existing is None:
                existing = Ingredient(source="restaurant", brand=cfg["brand"], name=name)
                db.add(existing)
                created += 1
            else:
                updated += 1
            for col, val in row.items():
                if val is not None:
                    setattr(existing, col, val)
            if not cfg["serving_is_grams"]:
                # No published gram weight: leave serving_size_g NULL and name
                # the serving, which the client treats as one named serving
                # rather than as per-100g. See buildServingOptions() in
                # AddFoodModal, and the serving-size invariant in CLAUDE.md.
                existing.serving_size_g = None
            existing.serving_size_desc = "1 serving"

        if args.dry_run:
            await db.rollback()
            print("(dry run — nothing written)")
        else:
            await db.commit()
            print(f"DONE  created={created} updated={updated}")

    if rejected:
        print(f"\nrejected {len(rejected)} (not imported):")
        for name, why in rejected[:15]:
            print(f"   {name[:46]:<48} {why}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
