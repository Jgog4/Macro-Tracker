"""
Import Chick-fil-A menu nutrition into mt_ingredients (source='restaurant').

Two public, documented endpoints are used — no scraping of rendered pages and no
private APIs:

  1. The site's WordPress REST API (`/wp-json/wp/v2/menu-item`) enumerates every
     menu item and gives its canonical URL.
  2. Each item page server-renders its own nutrition panel as embedded JSON:
       [{"key":"calories","value":420},{"key":"fat","value":"18g"}, ...]

robots.txt permits both paths (only /wp-admin/ is disallowed). Requests are
rate-limited and identify themselves honestly.

Chick-fil-A publishes per-item nutrition but not gram weights, so rows are
stored the way the app already handles that case: `serving_size_g = NULL` with a
`serving_size_desc`, which the client treats as a named serving rather than as
per-100 g. See buildServingOptions() in AddFoodModal.

Re-runnable: rows are matched on (brand, name) and updated in place.

    python scripts/import_restaurant_cfa.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import html as html_lib
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.models import Ingredient

BRAND = "Chick-fil-A"
BASE = "https://www.chick-fil-a.com"
UA = (
    "MacroTrackerPersonal/1.0 (personal nutrition tracker; "
    "contact: jessegoranson@gmail.com)"
)
DELAY = 1.0          # be a polite guest on someone else's server

# The embedded payload's keys → our columns. Values arrive as "18g" / "70mg" /
# a bare number for calories.
FIELD_MAP = {
    "calories":      "calories",
    "fat":           "fat_g",
    "saturated_fat": "sat_fat_g",
    "trans_fat":     "trans_fat_g",
    "cholesterol":   "cholesterol_mg",
    "sodium":        "sodium_mg",
    "carbs":         "carbs_g",
    "fiber":         "fiber_g",
    "sugar":         "sugar_g",
    "protein":       "protein_g",
}


def _number(value) -> float | None:
    """'18g' → 18.0, '1460mg' → 1460.0, 420 → 420.0, '' → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:\.\d+)?", str(value))
    return float(m.group()) if m else None


def parse_nutrition(html: str) -> dict[str, float] | None:
    """Pull the embedded nutrition array out of an item page."""
    m = re.search(r'\[\s*\{\s*"key"\s*:\s*"calories".*?\}\s*\]', html, re.S)
    if not m:
        return None
    try:
        rows = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out: dict[str, float] = {}
    for row in rows:
        col = FIELD_MAP.get(row.get("key"))
        val = _number(row.get("value"))
        if col and val is not None:
            out[col] = val
    return out or None


async def list_menu_items(client: httpx.AsyncClient) -> list[dict]:
    """
    Every menu URL, taken from the site's own sitemaps.

    robots.txt points at /sitemap_index.xml — using a site's published sitemap
    is the most explicitly-sanctioned way to enumerate its pages. The
    WordPress `menu-item` post type was tried first and rejected: it lists 567
    entries, but they are mostly components ("Filet", "Sausage") whose links go
    to the ordering app rather than to a page with a nutrition panel.
    """
    index = await client.get(f"{BASE}/sitemap_index.xml")
    index.raise_for_status()
    maps = re.findall(r"<loc>([^<]+)</loc>", index.text)

    urls: list[str] = []
    for sm in maps:
        if "menu-item-sitemap" not in sm and "page-sitemap" not in sm:
            continue
        r = await client.get(sm)
        if r.status_code != 200:
            continue
        urls.extend(re.findall(
            r"<loc>(https://www\.chick-fil-a\.com/menu/[^<]+)</loc>", r.text))
        await asyncio.sleep(DELAY)

    seen, out = set(), []
    for u in urls:
        u = u.rstrip("/")
        if u in seen:
            continue
        seen.add(u)
        slug = u.rsplit("/", 1)[-1]
        out.append({"link": u, "slug": slug})
    return out


def page_title(html: str) -> str | None:
    """The item's display name, from the page's own <title>/og:title."""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', html)
    if not m:
        m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if not m:
        return None
    title = m.group(1)
    # og:title carries marketing tails: "Chick-fil-A Nuggets | Delicious &
    # dippable", "Mac & Cheese Nutrition and Ingredients". Strip them so the
    # same item does not land in the library under two names.
    title = re.split(r"\s*[|–—]\s*", title)[0]
    title = re.sub(r"\s*\bNutrition(\s*(and|&)\s*Ingredients)?\s*$", "", title, flags=re.I)
    title = re.sub(r"\s*\bIngredients\s*$", "", title, flags=re.I)
    # Some og:titles append the brand after the tail:
    # "Chocolate Milkshake Nutrition and Ingredients Chick-fil-A".
    title = re.sub(r"\s*\bNutrition\s+(and|&)\s+Ingredients\b.*$", "", title, flags=re.I)
    title = re.sub(r"\s*\bChick-?fil-?A\s*$", "", title, flags=re.I).strip() or title
    return clean_title(title)


def clean_title(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    # html.unescape covers every entity; a hand-rolled list missed "&#039;"
    # and shipped items named "Kid&#039;s Meal".
    text = html_lib.unescape(html_lib.unescape(text))
    text = text.replace("\u00ae", "").replace("\u2122", "")
    return re.sub(r"\s+", " ", text).strip()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only process N items")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = create_async_engine(os.environ["DBURL"])
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with httpx.AsyncClient(
        timeout=25.0, follow_redirects=True,
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
    ) as client:
        items = await list_menu_items(client)
        print(f"menu items listed: {len(items)}")
        if args.limit:
            items = items[: args.limit]

        created = updated = skipped = 0
        seen_names: set[str] = set()
        async with Session() as db:
            for i, item in enumerate(items, 1):
                link = item["link"]
                try:
                    page = await client.get(link)
                    page.raise_for_status()
                    nutrition = parse_nutrition(page.text)
                    name = page_title(page.text) or clean_title(item["slug"].replace("-", " ").title())
                except httpx.HTTPError:
                    nutrition, name = None, item["slug"]

                if not nutrition or not nutrition.get("calories"):
                    skipped += 1
                    print(f"  [{i}/{len(items)}] – {name[:44]:<46} no nutrition on page")
                    await asyncio.sleep(DELAY)
                    continue

                key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
                if key in seen_names:
                    skipped += 1
                    print(f"  [{i}/{len(items)}] – {name[:44]:<46} duplicate of an earlier page")
                    await asyncio.sleep(DELAY)
                    continue
                seen_names.add(key)

                row = (await db.execute(
                    select(Ingredient).where(
                        Ingredient.brand == BRAND, Ingredient.name == name)
                )).scalar_one_or_none()

                if row is None:
                    row = Ingredient(
                        source="restaurant", brand=BRAND, name=name,
                        # Per-item values with no published gram weight: the
                        # client's serving-only path handles this correctly.
                        serving_size_g=None, serving_size_desc="1 serving",
                    )
                    db.add(row)
                    created += 1
                    tag = "new"
                else:
                    updated += 1
                    tag = "upd"
                for col, val in nutrition.items():
                    setattr(row, col, val)

                print(f"  [{i}/{len(items)}] {tag} {name[:44]:<46} "
                      f"{nutrition['calories']:.0f} kcal  P{nutrition.get('protein_g',0):.0f} "
                      f"F{nutrition.get('fat_g',0):.0f} C{nutrition.get('carbs_g',0):.0f}")
                await asyncio.sleep(DELAY)

            if args.dry_run:
                await db.rollback()
                print("\n(dry run — nothing written)")
            else:
                await db.commit()
                print(f"\nDONE  created={created} updated={updated} skipped={skipped}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
