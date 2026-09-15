"""
How much does one of something weigh?

Count-based ingredient lines — "2 apples", "1 courgette", "3 spring onions" —
are the long tail of recipe import, and a hand-written weight table cannot
cover them. USDA publishes household measures for essentially every whole food,
so this resolves weights from there on first use and caches the answer.

Three tiers, cheapest first:

  1. `mt_portion_weights` — already cached, or a weight the user typed by hand.
     User entries win permanently: their apples really may be bigger.
  2. The curated table in `units.py` — instant, no network, covers the foods
     that appear in almost every recipe.
  3. USDA FoodData Central household measures, then cached into tier 1.

Two things make tier 3 harder than it looks, and both are handled below:
USDA's search happily returns "Rose-apples, raw" for "apple" and "Sweet potato
leaves" for "sweet potato", and its portion modifiers mix whole items
("medium", "fruit without refuse") with quantities that are emphatically not
one item ("cup, chopped", "NLEA serving", "RACC").
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import PortionWeight
from app.services import units
from app.services.units import count_weight, item_weight_is_plausible

settings = get_settings()

SIZE_WORDS = ("extra large", "jumbo", "large", "medium", "small", "baby", "mini")

# Modifiers that describe a quantity of a food, not one of the food.
_NOT_ONE_ITEM = re.compile(
    r"\b(cup|cups|tbsp|tablespoon|tsp|teaspoon|oz|ounce|ml|litre|liter|gram|"
    r"slice|sliced|chopped|diced|mashed|pureed|shredded|grated|juice|halves|"
    r"pieces|cubes|strips|serving|racc|nlea|package|container|can|bottle|jar)\b",
    re.I,
)
# Modifiers that do mean one whole item.
_WHOLE_ITEM = re.compile(
    r"\b(each|whole|fruit|item|piece|medium|large|small|average|unit|"
    r"without refuse|edible portion)\b", re.I,
)


# Descriptions that are a different product from the raw ingredient. USDA's
# search puts "Chicken breast tenders, breaded" and "Marmalade, orange" above
# the plain food, and a portion read off those is meaningless.
_WRONG_FOOD = {
    "lunchmeat", "tenders", "breaded", "battered", "nuggets", "patty", "sausage",
    "marmalade", "jam", "jelly", "sherbet", "sorbet", "juice", "drink", "soda",
    "pickled", "canned", "dried", "candied", "sauce", "soup", "pie", "cake",
    "bar", "chips", "crisps", "powder", "extract", "oil", "baby", "infant",
}


# Must match mt_portion_weights.alias. A verbose recipe line ("organic
# free-range chicken breast, cut into 1-inch cubes") overflowed the column,
# which failed the flush and poisoned the whole request with
# PendingRollbackError — the import died on an incidental cache write.
_ALIAS_MAX = 200


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()[:_ALIAS_MAX]


def split_size(unit: Optional[str]) -> str:
    """Pull a size word out of the parsed unit ("large" from "2 large eggs")."""
    u = (unit or "").strip().lower()
    for s in SIZE_WORDS:
        if s in u:
            return s
    return ""


def pick_portion(portions: list[dict], size: str, food_name: str = "") -> Optional[float]:
    """
    Choose the gram weight of ONE item from a USDA foodPortions list.

    Returns None rather than guessing when nothing in the list describes a
    single item — a "cup, chopped" weight would be wildly wrong as an item.
    """
    scored: list[tuple[int, float]] = []
    for p in portions:
        gram = p.get("gramWeight")
        amt = p.get("amount") or 1
        if not gram or amt <= 0:
            continue
        per_item = gram / amt
        measure = ((p.get("measureUnit") or {}).get("name") or "").strip()
        modifier = (p.get("modifier") or "").strip()
        text = f"{measure} {modifier}".strip()
        if measure.lower() in ("undetermined", ""):
            text = modifier

        if _NOT_ONE_ITEM.search(text):
            continue

        low = text.lower()
        # A modifier that repeats the food's own name is describing one of
        # them: leek lists modifier "leek" = 89 g, eggplant lists "eggplant,
        # unpeeled (approx 1-1/4 lb)" = 548 g. This generalises far better than
        # any list of size words.
        names = {w for w in re.split(r"[^a-z0-9]+", _norm(food_name)) if len(w) > 3}
        says_itself = any(w in low or w.rstrip("s") in low for w in names)

        if size and size in low:
            rank = 0                       # exactly the size asked for
        elif says_itself:
            rank = 1
        elif _WHOLE_ITEM.search(text):
            rank = 1 if "medium" in low else 2
        else:
            # An unlabelled portion says nothing about being one item. Taking
            # it anyway produced "1 chicken breast = 15 g". Skip it and let the
            # review screen ask instead.
            continue
        scored.append((rank, per_item))

    if not scored:
        return None
    # Within a rank, prefer the LARGEST candidate: portion lists mix a whole
    # item with fragments of it, and the fragment is never the answer.
    scored.sort(key=lambda r: (r[0], -r[1]))
    return scored[0][1]


async def _usda_item_weight(name: str, size: str) -> Optional[float]:
    """Look up one item's weight from USDA, choosing the food carefully."""
    if not settings.USDA_API_KEY:
        return None
    query = _norm(name)
    if not query:
        return None
    want = {w.rstrip("s") for w in query.split()}

    def food_rank(f: dict) -> tuple:
        toks = [t for t in re.split(r"[^a-z0-9]+", (f.get("description") or "").lower()) if t]
        wrong = sum(1 for t in toks if t in _WRONG_FOOD and t not in want)
        head_hit = 0 if toks and toks[0].rstrip("s") in want else 1
        extra = len([t for t in toks if t.rstrip("s") not in want])
        return (wrong, head_hit, extra)

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # "raw" steers the search away from jams, sherbets and breaded
            # products, which otherwise outrank the plain ingredient.
            for q in (f"{query} raw", query):
                r = await client.get(
                    f"{settings.USDA_BASE_URL}/foods/search",
                    params={
                        "api_key": settings.USDA_API_KEY, "query": q,
                        "dataType": "SR Legacy,Foundation", "pageSize": 8,
                    },
                )
                r.raise_for_status()
                foods = sorted(r.json().get("foods") or [], key=food_rank)
                for food in foods[:3]:
                    if food_rank(food)[0]:        # still a wrong-product match
                        continue
                    d = await client.get(
                        f"{settings.USDA_BASE_URL}/food/{food['fdcId']}",
                        params={"api_key": settings.USDA_API_KEY},
                    )
                    d.raise_for_status()
                    grams = pick_portion(
                        d.json().get("foodPortions") or [], size, food.get("description", ""))
                    if grams:
                        return grams
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return None


_volume_cache: dict[tuple[str, str, str], Optional[float]] = {}


def _pick_volume_portion(portions: list[dict], unit: str, locale: str) -> Optional[float]:
    """Grams for one requested household-volume unit from USDA portions."""
    wanted = units.canonical_unit(unit)
    if wanted not in {"tsp", "tbsp", "cup", "floz", "ml", "l"}:
        return None
    candidates: list[float] = []
    for portion in portions:
        gram_weight = portion.get("gramWeight")
        amount = portion.get("amount") or 1
        if not gram_weight or amount <= 0:
            continue
        measure = ((portion.get("measureUnit") or {}).get("name") or "").lower()
        modifier = (portion.get("modifier") or "").lower()
        measure_unit = units.canonical_unit(measure)
        if measure_unit == wanted or wanted in f"{measure} {modifier}":
            candidates.append(float(gram_weight) / float(amount))
    if not candidates:
        return None
    # USDA household portions use US measures. Scale when the recipe expressly
    # uses metric, UK, or Australian household measures.
    scale = 1.0
    us_ml = units.volume_ml(1, wanted, "us")
    local_ml = units.volume_ml(1, wanted, locale)
    if us_ml and local_ml:
        scale = local_ml / us_ml
    return candidates[0] * scale


async def resolve_volume_weight(
    name: str, quantity: float, unit: str, locale: str = "us",
) -> Optional[float]:
    """Use a representative USDA household measure when the local food lacks one.

    This handles the long tail of "1/2 cup grated Parmesan"-style lines. It
    deliberately returns None on uncertainty rather than treating a volume as
    a countable object; callers can then request a manual weight.
    """
    if not settings.USDA_API_KEY or not quantity or quantity <= 0 or not units.is_volume_unit(unit):
        return None
    query = _norm(name)
    key = (query, units.canonical_unit(unit) or "", locale)
    if not query:
        return None
    if key in _volume_cache:
        per_unit = _volume_cache[key]
        return quantity * per_unit if per_unit else None

    want = {word.rstrip("s") for word in query.split()}

    def food_rank(food: dict) -> tuple:
        tokens = [word for word in re.split(r"[^a-z0-9]+", (food.get("description") or "").lower()) if word]
        wrong = sum(word in _WRONG_FOOD and word not in want for word in tokens)
        missing = sum(word not in {token.rstrip("s") for token in tokens} for word in want)
        head = 0 if tokens and tokens[0].rstrip("s") in want else 1
        return (wrong, missing, head, len(tokens))

    per_unit = None
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                f"{settings.USDA_BASE_URL}/foods/search",
                params={
                    "api_key": settings.USDA_API_KEY, "query": query,
                    "dataType": "SR Legacy,Foundation", "pageSize": 8,
                },
            )
            response.raise_for_status()
            foods = sorted(response.json().get("foods") or [], key=food_rank)
            for food in foods[:3]:
                if food_rank(food)[0] or food_rank(food)[1]:
                    continue
                detail = await client.get(
                    f"{settings.USDA_BASE_URL}/food/{food['fdcId']}",
                    params={"api_key": settings.USDA_API_KEY},
                )
                detail.raise_for_status()
                per_unit = _pick_volume_portion(
                    detail.json().get("foodPortions") or [], unit, locale
                )
                if per_unit:
                    break
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        per_unit = None
    _volume_cache[key] = per_unit
    return quantity * per_unit if per_unit else None


async def resolve_item_weight(
    db: AsyncSession, name: str, unit: Optional[str],
) -> tuple[Optional[float], str]:
    """
    Grams for one item of `name` at the given size.

    Returns (grams, source) where source is "user", "cache", "curated", "usda",
    or "unknown". Anything but "unknown" is safe to use; "unknown" means the
    review screen must ask.
    """
    alias = _norm(name)
    size = split_size(unit)
    if not alias:
        return None, "unknown"

    # 1. Read any cached/user-taught value, but do not trust it yet. Older
    # versions cached some USDA package weights as though they were one item.
    row = (await db.execute(
        select(PortionWeight).where(PortionWeight.alias == alias, PortionWeight.size == size)
    )).scalar_one_or_none()
    if row is None and size:
        row = (await db.execute(
            select(PortionWeight).where(PortionWeight.alias == alias, PortionWeight.size == "")
        )).scalar_one_or_none()
    if row and row.source == "user" and item_weight_is_plausible(name, unit, row.grams):
        return row.grams, ("user" if row.source == "user" else "cache")

    # 2. Curated item weights outrank third-party caches. These represent known
    # culinary units such as one egg, garlic clove, or dried bay leaf.
    hit = count_weight(name, unit)
    if hit is not None:
        return hit[0], "curated"

    # 3. A plausible non-user cache can now be reused.
    if row and item_weight_is_plausible(name, unit, row.grams):
        return row.grams, "cache"

    # 4. USDA, then remember it only if it is plausible for one item.
    grams = await _usda_item_weight(name, size)
    if grams and item_weight_is_plausible(name, unit, grams):
        await remember_weight(db, name, size, grams, source="usda")
        return grams, "usda"

    return None, "unknown"


async def remember_weight(
    db: AsyncSession, name: str, size: str, grams: float, source: str = "user",
) -> None:
    """
    Store a resolved or user-supplied item weight. User entries overwrite.

    Runs inside a SAVEPOINT. Caching a weight is incidental to the import, so a
    failure here must never take the request down with it — before this, one
    over-long name rolled back the whole transaction and every later query in
    the request failed with PendingRollbackError.
    """
    alias = _norm(name)
    if not alias or not grams or grams <= 0:
        return
    size = (size or "")[:40]
    try:
        async with db.begin_nested():
            row = (await db.execute(
                select(PortionWeight).where(
                    PortionWeight.alias == alias, PortionWeight.size == size)
            )).scalar_one_or_none()
            if row:
                if source == "user" or row.source != "user":
                    row.grams, row.source = float(grams), source
            else:
                db.add(PortionWeight(alias=alias, size=size,
                                     grams=float(grams), source=source))
    except SQLAlchemyError:
        pass          # the import continues without the cache entry
