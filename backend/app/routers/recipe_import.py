"""
/recipes/import — build a recipe from a URL or pasted ingredient text.

Pipeline: extract (stage 1) → parse lines (stage 2) → match to a verified food
(stage 3) → convert to grams (stage 4) → cooking transformations (stage 5) →
totals and save (stage 6).

Design decisions taken here, and why (the spec asks for these to be documented):

* **No bundled USDA dataset.** The spec suggests mirroring FoodData Central
  locally. This app already holds ~10,800 verified rows — Canadian Nutrient
  File, UK CoFID and USDA imports — behind a search endpoint that was recently
  tuned for relevance and recency, and it reaches the live USDA API for
  anything missing. Bundling a multi-hundred-megabyte dataset into a
  single-user Railway deployment would add real ops burden for a marginal
  coverage gain. Household measures are fetched per matched food and cached.
* **No embeddings.** Matching reuses the existing Postgres search (trigram
  fuzzy + word-start relevance + usage recency) plus a synonym table. An
  embedding index is not justified at this corpus size.
* **Nutrition never comes from the model.** The parser returns structure only;
  every number below is read off a matched database row.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import Ingredient, IngredientAlias, Recipe, RecipeImportLog, User
from app.schemas.recipe_import import PreviewRequest, SaveRequest
from app.services import units
from app.services.portions import (
    remember_weight, resolve_item_weight, resolve_volume_weight, split_size,
)
from app.services.recipe_import import ExtractionFailed, extract_recipe, parse_ingredient_lines

settings = get_settings()
router = APIRouter(prefix="/recipes/import", tags=["Recipe import"])

DEFAULT_USER_EMAIL = "jesse@macro.app"

# Synonyms that change which database row matches. Regional naming is a chronic
# weakness in US-centric trackers — "capsicum" finds nothing in USDA.
_SYNONYMS = {
    "scallion": "green onion", "spring onion": "green onion",
    "capsicum": "bell pepper", "aubergine": "eggplant", "courgette": "zucchini",
    "coriander leaves": "cilantro", "fresh coriander": "cilantro",
    "caster sugar": "superfine sugar", "icing sugar": "powdered sugar",
    "plain flour": "all-purpose flour", "cornflour": "cornstarch",
    "beef mince": "ground beef", "pork mince": "ground pork",
    "minced beef": "ground beef", "double cream": "heavy cream",
    "single cream": "light cream", "rocket": "arugula", "swede": "rutabaga",
    "prawns": "shrimp", "natural yoghurt": "plain yogurt", "yoghurt": "yogurt",
    "streaky bacon": "bacon", "gammon": "ham", "chips": "french fries",
}

# Adjectives that describe handling, not identity. Left in the query they pull
# matches toward whatever long branded name happens to contain them — "clear
# honey" matched "Oil, industrial, soy" on the word "clear".
_NOISE_WORDS = {
    "fresh", "clear", "large", "small", "medium", "chopped", "finely",
    "roughly", "thinly", "sliced", "diced", "grated", "shredded", "minced",
    "crushed", "good", "quality", "best", "free", "range", "organic",
    "unsalted", "salted", "plus", "more", "extra", "pack", "packet", "punnet",
    "leaves", "leaf", "sprigs", "handful", "knob", "splash", "drizzle",
}


# Words that mean the candidate is a *different product* from the plain
# ingredient asked for. Without this, "mozzarella" lands on "Mozzarella sticks,
# fried" and "beef" on "Beef extract" — both are shorter names that happen to
# contain the word.
_PREPARATION_WORDS = {
    "fried", "breaded", "battered", "sticks", "dip", "sauce", "soup", "powder", "dry",
    "extract", "dehydrated", "syrup", "snack", "bar", "pie", "cake", "roll",
    "juice", "drink", "flavoured", "flavored", "substitute", "imitation",
    "baby", "babyfood", "infant",
    # Dish names. A recipe asking for "eggs" means the ingredient, not
    # "Egg Benedict" or "Egg nog" — both of which lead with the right word.
    "benedict", "nog", "eggnog", "salad", "casserole", "stew", "curry",
    "sandwich", "burger", "wrap", "quiche", "omelette", "omelet", "scrambled",
    "poached", "boiled", "pickled", "smoothie", "yung", "custard", "bagel",
    "cracker", "bread", "muffin", "pudding", "pancake",
    # Parts of a food are different products from the whole thing. "eggs"
    # must not land on "Eggs, chicken, yolk, raw". These only count when the
    # query did NOT ask for them, so "white rice" is unaffected.
    "yolk", "white", "albumen", "shell", "skin", "peel", "rind", "core", "stalk",
}

_PY_SOURCE_RANK = {"cnf": 0, "cofid": 0, "usda": 0, "personal": 1, "custom": 2, "restaurant": 3}

# When a recipe says "eggs" it means hen's eggs, but the database lists duck,
# quail, goose and turkey alongside — and those names are shorter, so they win
# any tie broken on length. These are the implied varieties for generics whose
# databases enumerate species.
_IMPLIED_VARIETY = {
    "egg": "chicken", "eggs": "chicken",
    # A plain recipe line such as "2 cups milk (any fat %)" needs a liquid
    # default. Whole milk is the conventional cooking baseline; a dry/powdered
    # milk product is a different ingredient and must be stated explicitly.
    "milk": "whole", "flour": "wheat", "rice": "white",
}


def _word_variants(word: str) -> list[str]:
    """
    A word plus its singular/plural twin.

    Databases disagree on number: CNF writes "Egg, chicken, whole, raw" while
    CoFID writes "Eggs, duck, whole, raw". Matching "eggs" literally could only
    ever reach the plural rows, so a recipe calling for eggs matched "Scotch
    eggs, retail" and the correct entry was never even a candidate.
    """
    w = word.lower()
    out = {w}
    if w.endswith("ies") and len(w) > 4:
        out.add(w[:-3] + "y")
    elif w.endswith("es") and len(w) > 3:
        out.add(w[:-2]); out.add(w[:-1])
    elif w.endswith("s") and len(w) > 3:
        out.add(w[:-1])
    else:
        out.add(w + "s")
        if w.endswith("y") and len(w) > 3:
            out.add(w[:-1] + "ies")
    return sorted(out, key=len, reverse=True)


def _fold(text: str) -> str:
    """Strip accents so 'crème fraîche' can match 'creme fraiche'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", (text or "").lower())
        if not unicodedata.combining(c)
    )


# Prep words that must agree between the parsed line and the matched food.
_PREP_WORDS = {
    "cooked":  ("cooked", "boiled", "roasted", "braised"),
    "dry":     ("dry", "raw", "uncooked"),
    "canned":  ("canned", "tinned"),
    "drained": ("drained",),
    "raw":     ("raw",),
}

_MAX_LINE_KCAL      = 2000    # spec sanity thresholds
_MAX_SERVING_KCAL   = 2500
_MIN_SERVING_KCAL   = 20
_CONFIDENCE_FLOOR   = 0.8

_portion_cache: dict[int, list[dict]] = {}


# ── helpers ──────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    # Capped to mt_ingredient_aliases.alias; see portions._norm for why.
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()[:300]


def _expand_synonyms(name: str) -> str:
    n = name.lower()
    for src, dst in _SYNONYMS.items():
        if src in n:
            n = n.replace(src, dst)
    return n


async def _get_user(db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.email == DEFAULT_USER_EMAIL))).scalar_one_or_none()
    if not user:
        user = User(email=DEFAULT_USER_EMAIL, name="Jesse")
        db.add(user)
        await db.flush()
    return user


async def _usda_portions(fdc_id: int) -> list[dict]:
    """Household measures for one USDA food ("1 cup, chopped = 160 g"), cached."""
    if fdc_id in _portion_cache:
        return _portion_cache[fdc_id]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.USDA_BASE_URL}/food/{fdc_id}",
                params={"api_key": settings.USDA_API_KEY},
            )
            r.raise_for_status()
            portions = r.json().get("foodPortions") or []
    except (httpx.HTTPError, ValueError, KeyError):
        portions = []
    _portion_cache[fdc_id] = portions
    return portions


def _prep_score(food_name: str, prep_state: Optional[str]) -> int:
    """
    Reward a candidate whose cooking state agrees with the parsed line.

    Cooked and raw values differ by 30-40% per gram through water loss, so a
    state mismatch is a bigger error than a slightly different cut.
    """
    if not prep_state:
        return 0
    n = (food_name or "").lower()
    wanted = _PREP_WORDS.get(prep_state, ())
    if any(w in n for w in wanted):
        return 2
    # Actively penalise the opposite state.
    opposite = ("cooked",) if prep_state in ("dry", "raw") else ("raw", "dry", "uncooked")
    if any(w in n for w in opposite):
        return -2
    return 0



# Sources that must never be offered as a recipe ingredient.
#   estimated_component — fragments of past AI meal estimates ("Garlic mayo
#     sauce (side dip)"). They matched "garlic" and "basil" in testing and are
#     one-off composites, not generic foods.
#   barcode — scanned products kept out of the library on purpose.
_EXCLUDED_SOURCES = ("estimated_component", "barcode")


async def _search_candidates(db: AsyncSession, query: str, prep: Optional[str] = None,
                             limit: int = 6) -> list[Ingredient]:
    """
    Ingredient matching for recipe import.

    Deliberately NOT the app's normal food search. That one ranks your own most
    recently eaten foods first, which is right for logging and wrong here: a
    recipe line saying "beef mince" wants the generic lab-analysed entry, not
    the "Ground beef red sauce" you ate on Tuesday. So verified generics
    (CNF / CoFID / USDA) sort first, and the shortest name wins ties — "Garlic"
    beats "Garlic mayo sauce (side dip)".
    """
    folded = _fold(query)
    words  = [w for w in re.split(r"[^a-z0-9]+", folded) if len(w) > 1]
    content = [w for w in words if w not in _NOISE_WORDS]
    words = content or words          # never search on nothing
    if not words:
        return []
    clauses = []
    for w in words:
        # Word-boundary regex, not substring: `contains("salt")` matched
        # "Butter, unsalted", so a pinch of salt offered butter as its top
        # alternatives. \y is Postgres's word boundary.
        pattern = r"\y(" + "|".join(re.escape(v) for v in _word_variants(w)) + r")\y"
        clauses.append(or_(
            func.lower(func.unaccent(Ingredient.name)).op("~")(pattern),
            func.lower(func.unaccent(func.coalesce(Ingredient.brand, ""))).op("~")(pattern),
        ))
    source_rank = case(
        (Ingredient.source == "cnf",        0),   # lab-analysed generics first
        (Ingredient.source == "cofid",      0),
        (Ingredient.source == "usda",       0),
        (Ingredient.source == "personal",   1),
        (Ingredient.source == "custom",     2),
        (Ingredient.source == "restaurant", 3),
        else_=4,
    )
    stmt = (
        select(Ingredient)
        .where(and_(*clauses))
        .where(Ingredient.recipe_id.is_(None))
        .where(Ingredient.source.notin_(_EXCLUDED_SOURCES))
        .where(Ingredient.calories.is_not(None))
        .order_by(source_rank, func.length(Ingredient.name), Ingredient.name)
        .limit(limit * 12)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if rows:
        return _rank(rows, words, prep)[:limit]
    # Fall back to the whole phrase if the AND across words was too strict.
    phrase = query.lower().strip()
    stmt = (
        select(Ingredient)
        .where(func.lower(Ingredient.name).contains(phrase))
        .where(Ingredient.recipe_id.is_(None))
        .where(Ingredient.source.notin_(_EXCLUDED_SOURCES))
        .where(Ingredient.calories.is_not(None))
        .order_by(source_rank, func.length(Ingredient.name))
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


def _rank(rows: list[Ingredient], words: list[str], prep: Optional[str] = None) -> list[Ingredient]:
    """
    Prefer the candidate that says the least beyond what was asked for.

    Ordering, in priority: verified generic source, then no unrequested
    preparation ("sticks, fried", "extract"), then fewest extra words, then the
    food's head noun matching. Sorting by raw string length alone put "Creamy
    Parmesan Dip" above "Cheese, parmesan, hard".
    """
    # Compare on variants so "egg" in a candidate satisfies a query for "eggs".
    wanted = {v for w in words for v in _word_variants(w)}
    implied = next((_IMPLIED_VARIETY[w] for w in words if w in _IMPLIED_VARIETY), None)
    if implied:
        wanted.add(implied)      # so naming it is not counted as an extra word

    def key(food: Ingredient) -> tuple:
        toks = [t for t in re.split(r"[^a-z0-9]+", _fold(food.name)) if t]
        unmatched = [t for t in toks if t not in wanted]
        prep_noise = sum(1 for t in unmatched if t in _PREPARATION_WORDS)
        # The head noun is what the food IS. "Egg, chicken, whole, raw" leads
        # with the thing asked for; "Scotch eggs, retail" leads with something
        # else and merely mentions it. That outranks having fewer extra words,
        # or the longer-but-correct generic always loses to a short wrong one.
        head_hit = 0 if toks and toks[0] in wanted else 1
        # The parsed line knows the state the ingredient is used in. Preferring
        # a candidate that says so is what separates "Egg, chicken, whole, raw"
        # from "Egg Benedict" when both lead with "egg".
        prep_hit = 0 if (prep and any(w in toks for w in _PREP_WORDS.get(prep, ()))) else 1
        # Prefer the implied default variety over an enumerated exotic one.
        implied_hit = 0 if (implied is None or implied in toks) else 1
        # Food identity comes before source preference. A verified generic is
        # valuable, but it must not beat the correct form of the ingredient:
        # e.g. "Milk, dry whole" is not a safe default for plain liquid milk.
        return (prep_noise, head_hit, prep_hit, implied_hit,
                _PY_SOURCE_RANK.get(food.source, 4), len(unmatched), len(food.name or ""))
    return sorted(rows, key=key)


async def _match_ingredient(db: AsyncSession, user: User, line: dict) -> tuple[Optional[Ingredient], list[Ingredient]]:
    """Alias table first, then local verified search.

    A live USDA result is never selected automatically. Search ordering can put a
    similarly named branded product first, so importing it without review turns
    a plausible match into quietly incorrect nutrition.
    """
    name  = line.get("name") or line.get("raw") or ""
    alias = _normalise(name)

    # 1. A correction the user already made wins outright.
    if alias:
        hit = (await db.execute(
            select(IngredientAlias).where(
                IngredientAlias.user_id == user.id, IngredientAlias.alias == alias)
        )).scalar_one_or_none()
        if hit:
            ing = await db.get(Ingredient, hit.ingredient_id)
            if ing:
                return ing, [ing]

    query = _expand_synonyms(name)
    prep  = line.get("prep_state")
    terms = f"{query} {prep}".strip() if prep else query

    cands: list[Ingredient] = []
    for q in (terms, query):
        if not q.strip():
            continue
        cands = await _search_candidates(db, q, prep)
        if cands:
            break

    if not cands:
        return None, []

    cands.sort(key=lambda c: -_prep_score(c.name, prep))
    return cands[0], cands[:5]


def _per_gram(food: Ingredient) -> dict[str, float]:
    """Nutrition per gram. Honours the app-wide serving-size invariant."""
    base = food.serving_size_g or 100.0
    if base <= 0:
        base = 100.0
    def v(attr): return (getattr(food, attr, None) or 0.0) / base
    return {
        "calories": v("calories"), "protein_g": v("protein_g"), "fat_g": v("fat_g"),
        "carbs_g": v("carbs_g"), "sodium_mg": v("sodium_mg"),
        "cholesterol_mg": v("cholesterol_mg"), "fiber_g": v("fiber_g"),
        "sugar_g": v("sugar_g"), "sat_fat_g": v("sat_fat_g"),
    }


# ── request / response models ────────────────────────────────────────────────

# ── stage 5: cooking transformations ─────────────────────────────────────────

def _cooking_adjustments(instructions: str, lines: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Apply the two transformations that actually move the numbers, and say so.

    Where the method can't be inferred we deliberately do nothing and surface a
    note — a visible "computed from raw ingredient weights" beats a hidden
    wrong adjustment.
    """
    notes: list[str] = []
    inst = (instructions or "").lower()
    drains_fat = bool(re.search(r"drain(ing|ed)?\s+(off\s+)?(the\s+)?(excess\s+)?(fat|grease)", inst))

    for ln in lines:
        nm = (ln.get("name") or "").lower()
        is_ground_meat = any(w in nm for w in ("ground beef", "ground pork", "beef mince",
                                               "ground lamb", "ground turkey", "mince"))
        if drains_fat and is_ground_meat and ln.get("nutrition"):
            removed = ln["nutrition"]["fat_g"] * 0.5          # default 50%, editable
            ln["nutrition"]["fat_g"] -= removed
            ln["nutrition"]["calories"] -= removed * 9
            ln.setdefault("flags", []).append("fat_drained")
            ln["fat_retention"] = 0.5
            ln["adjustment_note"] = (
                f"Instructions say the fat is drained — removed {removed:.0f} g fat "
                f"(50% of rendered fat, editable)."
            )
            notes.append(f"{ln['name']}: drained fat assumption applied.")

    if not notes:
        notes.append("Computed from raw ingredient weights — no cooking adjustment applied.")
    return lines, notes


# ── endpoints ────────────────────────────────────────────────────────────────

@router.post("/preview")
async def preview_import(body: PreviewRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Run the whole pipeline and return a draft for the review screen."""
    try:
        extracted = await extract_recipe(url=body.url, text=body.text)
    except ExtractionFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        if len(extracted["ingredients"]) > 250:
            raise ExtractionFailed("Recipes are limited to 250 ingredient lines.")
        parsed = await parse_ingredient_lines(extracted["ingredients"], extracted.get("instructions", ""))
    except ExtractionFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail="Ingredient parsing is temporarily unavailable. Please try again.",
        ) from exc

    user = await _get_user(db)
    lines: list[dict] = []

    for p in parsed:
        food, alternates = await _match_ingredient(db, user, p)
        # An "A or B" source line is one ingredient choice, never two full
        # quantities. Resolve each option up front so the review can offer a
        # one-tap substitution without leaving the primary choice unmatched.
        ingredient_options = []
        option_names = [p.get("name") or "", *(p.get("alternatives") or [])]
        for option_name in option_names[:4]:
            option_line = {**p, "name": option_name, "alternatives": []}
            option_food, option_alternates = (
                (food, alternates) if option_name == p.get("name")
                else await _match_ingredient(db, user, option_line)
            )
            ingredient_options.append((option_name, option_food, option_alternates))
        portions = []
        if food is not None and getattr(food, "usda_fdc_id", None):
            portions = await _usda_portions(food.usda_fdc_id)

        grams, method = units.to_grams(
            p.get("quantity"), p.get("unit"), p.get("name") or "",
            usda_portions=portions, locale=body.locale,
        )
        # CNF/CoFID foods do not carry an FDC id and therefore lack household
        # portions. For an unfamiliar cup/spoon measure, ask USDA for a
        # representative generic portion before asking the user. A volume must
        # never be sent through the whole-item resolver below.
        is_volume = units.is_volume_unit(p.get("unit"))
        if grams is None and is_volume and p.get("quantity"):
            grams = await resolve_volume_weight(
                _expand_synonyms(p.get("name") or ""), p["quantity"],
                p.get("unit") or "", body.locale,
            )
            if grams is not None:
                method = "usda_volume"
        # Count-based lines ("2 apples") rarely resolve from the matched food:
        # CNF and CoFID rows carry no USDA id and so no household measures.
        # Fall back to the shared resolver, which caches and learns.
        if grams is None and not is_volume and p.get("quantity") and method != "imprecise":
            per_item, src = await resolve_item_weight(
                db, _expand_synonyms(p.get("name") or ""), p.get("unit"))
            if per_item:
                grams = p["quantity"] * per_item
                # Namespaced so the review screen can tell a *stated* weight
                # from an *inferred* one. Only a weight you taught it yourself
                # is trusted without a second look.
                method = f"item:{src}"

        nutrition = None
        if food is not None and grams:
            pg = _per_gram(food)
            nutrition = {k: v * grams for k, v in pg.items()}

        flags = list(p.get("flags") or [])
        # Optional and garnish default OFF; to-taste defaults ON at a token amount.
        include = not any(f in flags for f in ("optional", "garnish", "sub_recipe"))
        if "to_taste" in flags and grams is None:
            grams, method, include = 1.0, "to_taste", True

        needs_review = (
            food is None or grams is None
            # A match with no nutrition data would silently contribute zero —
            # worse than no match, because it looks resolved.
            or nutrition is None or not nutrition.get("calories")
            or p.get("confidence", 0) < _CONFIDENCE_FLOOR
            # An inferred per-item weight is a guess, however well sourced.
            # "1 peach" resolved to 35 g in testing — plausible-looking and
            # wrong. Surface it once; teaching it a weight settles it for good.
            or (method.startswith("item:") and method != "item:user")
            or method == "count_default"
            or bool(set(flags) & {"optional", "garnish", "to_taste", "partial_use",
                                  "sub_recipe", "range"})
        )
        if nutrition and nutrition["calories"] > _MAX_LINE_KCAL:
            flags.append("calorie_outlier")
            needs_review = True

        lines.append({
            "raw":            p["raw"],
            "name":           p["name"],
            "quantity":       p.get("quantity"),
            "unit":           p.get("unit"),
            "prep_state":     p.get("prep_state"),
            "flags":          flags,
            "confidence":     p.get("confidence"),
            "grams":          round(grams, 1) if grams else None,
            "gram_method":    method,
            "include":        include,
            "needs_review":   needs_review,
            "match": None if food is None else {
                "id": food.id, "name": food.name, "brand": food.brand,
                "source": food.source, "per_gram": _per_gram(food),
            },
            "alternates": [
                {"id": a.id, "name": a.name, "brand": a.brand,
                 "source": a.source, "per_gram": _per_gram(a)}
                for a in alternates
            ],
            "ingredient_options": [
                {
                    "name": option_name,
                    "match": None if option_food is None else {
                        "id": option_food.id, "name": option_food.name,
                        "brand": option_food.brand, "source": option_food.source,
                        "per_gram": _per_gram(option_food),
                    },
                    "alternates": [
                        {"id": a.id, "name": a.name, "brand": a.brand,
                         "source": a.source, "per_gram": _per_gram(a)}
                        for a in option_alternates
                    ],
                }
                for option_name, option_food, option_alternates in ingredient_options
            ],
            "nutrition": nutrition,
            "fat_retention": 1.0,
        })

    lines, cooking_notes = _cooking_adjustments(extracted.get("instructions", ""), lines)

    # Default serving count from recipeYield ("Serves 6", "6", "Cuts into 16 …").
    servings = 1
    m = re.search(r"\d+", extracted.get("yield") or "")
    if m:
        servings = max(1, min(60, int(m.group())))

    totals = {k: 0.0 for k in ("calories", "protein_g", "fat_g", "carbs_g",
                               "sodium_mg", "cholesterol_mg", "fiber_g", "sugar_g", "sat_fat_g")}
    total_g = 0.0
    for ln in lines:
        if ln["include"] and ln["nutrition"]:
            for k in totals:
                totals[k] += ln["nutrition"].get(k, 0.0)
            total_g += ln["grams"] or 0.0

    warnings = []
    per_serving_kcal = totals["calories"] / max(1, servings)
    if per_serving_kcal > _MAX_SERVING_KCAL:
        warnings.append(f"{per_serving_kcal:.0f} kcal per serving looks high — check for a unit or match error.")
    if 0 < per_serving_kcal < _MIN_SERVING_KCAL:
        warnings.append(f"{per_serving_kcal:.0f} kcal per serving looks low — check the matches.")
    unmatched = sum(1 for l in lines if not l["match"])
    if unmatched:
        warnings.append(f"{unmatched} ingredient(s) could not be matched to a food.")

    log = RecipeImportLog(
        user_id=user.id, source_url=extracted.get("source_url"), method=extracted.get("method"),
        title=(extracted.get("title") or "")[:500], line_count=len(lines),
        payload={"yield": extracted.get("yield"), "lines": lines},
    )
    db.add(log)
    await db.flush()

    return {
        "import_id":    log.id,
        "title":        extracted.get("title"),
        "source_url":   extracted.get("source_url"),
        "method":       extracted.get("method"),
        "yield_text":   extracted.get("yield"),
        "num_servings": servings,
        "lines":        lines,
        "totals":       {k: round(v, 2) for k, v in totals.items()},
        "total_weight_g": round(total_g, 1),
        "cooking_notes": cooking_notes,
        "warnings":     warnings,
    }


@router.post("/save")
async def save_import(body: SaveRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Persist the reviewed draft as a normal recipe, and learn any corrections."""
    from app.models.models import RecipeIngredient
    from app.routers.recipes import _compute_recipe_totals

    user = await _get_user(db)
    pairs: list[tuple[Ingredient, float, float]] = []
    invalid_lines: list[str] = []

    for ln in body.lines:
        if not ln.include:
            continue
        if not ln.ingredient_id:
            invalid_lines.append(f"{ln.name}: choose a matching food")
            continue
        if ln.grams is None:
            invalid_lines.append(f"{ln.name}: enter a gram weight")
            continue
        food = await db.get(Ingredient, ln.ingredient_id)
        if food is None:
            invalid_lines.append(f"{ln.name}: selected food no longer exists")
            continue
        if food.recipe_id is not None:
            invalid_lines.append(f"{ln.name}: another recipe cannot be used as an ingredient")
            continue
        pairs.append((food, float(ln.grams), float(ln.fat_retention)))
        # Only a weight the person actually changed is a preference. Previously
        # every inferred per-item value was saved as a user value on submit;
        # one bad parse of "2 tsp oregano" could therefore teach the importer
        # that one oregano weighs 35 g forever.
        if (ln.weight_was_edited and ln.quantity and ln.quantity > 0
                and not ln.unit_is_mass):
            await remember_weight(db, ln.name, split_size(ln.unit),
                                  float(ln.grams) / ln.quantity, source="user")
        if ln.alias_learn:
            alias = _normalise(ln.name)
            if alias:
                existing = (await db.execute(
                    select(IngredientAlias).where(
                        IngredientAlias.user_id == user.id, IngredientAlias.alias == alias)
                )).scalar_one_or_none()
                if existing:
                    existing.ingredient_id = ln.ingredient_id
                    existing.hits = (existing.hits or 1) + 1
                else:
                    db.add(IngredientAlias(user_id=user.id, alias=alias,
                                           ingredient_id=ln.ingredient_id))

    if invalid_lines:
        raise HTTPException(
            status_code=422,
            detail="Fix these included ingredients before saving: " + "; ".join(invalid_lines[:10]),
        )
    if not pairs:
        raise HTTPException(status_code=422, detail="Include at least one matched ingredient.")

    totals = _compute_recipe_totals(pairs)
    servings = body.num_servings
    # `serving_size_g` on a recipe is the finished weight of the WHOLE recipe,
    # not one serving — RecipeBuilderModal stores the cooked weight there and
    # the client divides by num_servings itself. Writing a per-serving value
    # here made the client divide twice, so a 12-serving pudding reported
    # 2,942 kcal/100 g instead of 247.
    finished = body.cooked_weight_g or totals["total_weight_g"]

    recipe = Recipe(
        name=body.title.strip(),
        source_url=body.source_url,
        num_servings=servings,
        total_weight_g=totals["total_weight_g"],
        serving_size_g=round(finished, 2) if finished else None,
        calories=totals["calories"], protein_g=totals["protein_g"],
        fat_g=totals["fat_g"], carbs_g=totals["carbs_g"],
        sodium_mg=totals["sodium_mg"], cholesterol_mg=totals["cholesterol_mg"],
    )
    db.add(recipe)
    await db.flush()
    for food, qty, fat_retention in pairs:
        db.add(RecipeIngredient(
            recipe_id=recipe.id, ingredient_id=food.id, quantity_g=qty,
            fat_retention=fat_retention,
        ))

    if body.import_id:
        log = await db.get(RecipeImportLog, body.import_id)
        if log and log.user_id == user.id:
            log.recipe_id = recipe.id

    await db.flush()
    return {
        "id": recipe.id, "name": recipe.name, "num_servings": recipe.num_servings,
        "serving_size_g": recipe.serving_size_g, "total_weight_g": recipe.total_weight_g,
        "calories": recipe.calories, "protein_g": recipe.protein_g,
        "fat_g": recipe.fat_g, "carbs_g": recipe.carbs_g,
    }
