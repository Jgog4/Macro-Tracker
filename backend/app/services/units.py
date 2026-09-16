"""
Quantity → grams conversion for recipe import.

The three-tier strategy from the spec, in priority order:

  1. A food-specific household measure from USDA ("1 cup chopped onion = 160 g").
     Always preferred — it is measured, not derived.
  2. A curated density table, so volume→weight works at all. This is the
     conversion MyFitnessPal refuses to do: it converts cups→tbsp but not
     cups→grams, which makes every volumetric ingredient a manual entry.
  3. Give up and ask, returning None so the review screen can prompt. Never
     guess silently for something that carries meaningful calories.

Locale matters more than it looks: a "tablespoon" is 14.79 mL in the US, 15 mL
in the UK/metric, and 20 mL in Australia. A US-centric converter silently
inflates or deflates every Australian recipe by a third on every tbsp line.
"""
from __future__ import annotations

import re
from typing import Optional

# ── Volume units → millilitres, by locale ────────────────────────────────────
# "cup" is the other trap: 236.6 mL US, 250 mL metric/AU, 284 mL imperial (UK
# historically, though modern UK recipes use 250).
_VOLUME_ML = {
    "us":     {"tsp": 4.929, "tbsp": 14.787, "cup": 236.588, "floz": 29.574},
    "metric": {"tsp": 5.0,   "tbsp": 15.0,   "cup": 250.0,   "floz": 30.0},
    "uk":     {"tsp": 5.0,   "tbsp": 15.0,   "cup": 250.0,   "floz": 28.413},
    "au":     {"tsp": 5.0,   "tbsp": 20.0,   "cup": 250.0,   "floz": 30.0},
}
DEFAULT_LOCALE = "us"

# Imprecise seasoning amounts. These are not countable items, so they must not
# reach the per-item resolver — "1 pinch salt" came back as 35 g from a USDA
# portion lookup, which is roughly a hundred pinches.
IMPRECISE_G = {"pinch": 0.36, "dash": 0.6, "smidgen": 0.2, "drop": 0.05, "sprinkle": 0.5}

# Fixed-weight units need no density.
_MASS_G = {"g": 1.0, "kg": 1000.0, "mg": 0.001, "oz": 28.3495, "lb": 453.592}
_VOLUME_UNITS = {"tsp", "tbsp", "cup", "floz", "ml", "l"}

# Unit spelling → canonical token.
_UNIT_ALIASES = {
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "t": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbs": "tbsp", "tb": "tbsp", "T": "tbsp",
    "cup": "cup", "cups": "cup", "c": "cup",
    "fluid ounce": "floz", "fluid ounces": "floz", "fl oz": "floz", "floz": "floz",
    "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml", "ml": "ml",
    "litre": "l", "litres": "l", "liter": "l", "liters": "l", "l": "l",
    "gram": "g", "grams": "g", "g": "g", "gr": "g",
    "kilogram": "kg", "kilograms": "kg", "kg": "kg",
    "milligram": "mg", "milligrams": "mg", "mg": "mg",
    "ounce": "oz", "ounces": "oz", "oz": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
}

# ── Density table (g/mL) ─────────────────────────────────────────────────────
# Keyed by substring match against the ingredient name, longest match first.
# Values are standard culinary references; flours and sugars vary with packing,
# which is exactly why a USDA household measure is preferred when one exists.
_DENSITY = {
    # USDA gives 125 g per US cup for white all-purpose flour; 125/236.588 =
    # 0.528. Deriving these from a known cup weight rather than eyeballing keeps
    # the density table honest against the household measures it stands in for.
    "bread flour": 0.55, "all-purpose flour": 0.528, "all purpose flour": 0.528,
    "plain flour": 0.528, "cake flour": 0.45, "whole wheat flour": 0.51,
    "almond flour": 0.40, "cornstarch": 0.51, "cocoa powder": 0.42, "flour": 0.528,
    "icing sugar": 0.56, "powdered sugar": 0.56, "confectioners sugar": 0.56,
    "brown sugar": 0.85, "caster sugar": 0.90, "granulated sugar": 0.85, "sugar": 0.85,
    "honey": 1.42, "maple syrup": 1.32, "molasses": 1.40, "corn syrup": 1.38,
    "olive oil": 0.918, "vegetable oil": 0.92, "canola oil": 0.92,
    "coconut oil": 0.92, "sesame oil": 0.92, "oil": 0.92,
    "ghee": 0.911, "butter": 0.911, "margarine": 0.91,
    "milk": 1.03, "buttermilk": 1.03, "cream": 1.00, "yogurt": 1.03, "yoghurt": 1.03,
    "water": 1.0, "stock": 1.0, "broth": 1.0, "juice": 1.04, "vinegar": 1.01,
    "soy sauce": 1.15, "fish sauce": 1.20, "ketchup": 1.14,
    # Tomato paste is much denser than fresh tomato. Three US tablespoons are
    # about 49 g, not three whole tomatoes (369 g).
    "tomato paste": 1.10, "tomato puree": 1.06, "passata": 1.04,
    "mayonnaise": 0.91, "peanut butter": 1.08, "tahini": 1.05,
    "rice": 0.85, "oats": 0.41, "rolled oats": 0.41, "breadcrumbs": 0.43,
    "salt": 1.22, "kosher salt": 0.69, "baking powder": 0.90, "baking soda": 1.10,
    # Small-volume flavourings. Without these a "2 tsp vanilla extract" line
    # has no way to become grams and stalls the review screen for ~10 kcal.
    "vanilla extract": 0.88, "almond extract": 0.88, "extract": 0.88,
    "worcestershire": 1.10, "mustard": 1.05, "hot sauce": 1.01, "sriracha": 1.10,
    "maple": 1.32, "syrup": 1.33, "jam": 1.33, "treacle": 1.42,
    # Cheese is usually stated by a preparation-specific household measure.
    # One US cup of finely grated Parmesan is about 100 g, so 1/2 cup is 50 g.
    "grated parmesan": 0.423, "parmesan cheese": 0.423, "parmesan": 0.423,
    "shredded cheese": 0.48, "grated cheese": 0.42, "cream cheese": 0.96,
    "ricotta": 0.99, "cottage cheese": 0.95,
    # Dried herbs and ground spices are extremely light by volume.  Treating
    # them as countable foods makes "2 tsp dried oregano" fall through to an
    # unrelated remembered per-item weight (e.g. 70 g), which is wildly wrong.
    # These values are grams per mL, based on common teaspoon weights.
    "minced garlic": 0.57, "fresh garlic": 0.57, "garlic": 0.57,
    "garam masala": 0.38, "ground coriander": 0.36, "coriander seed": 0.36,
    "ground cardamom": 0.40, "cardamom": 0.40,
    "fresh cilantro": 0.068, "cilantro": 0.068,
    "fresh coriander": 0.068, "coriander leaves": 0.068,
    "italian seasoning": 0.20, "dried oregano": 0.20, "oregano": 0.20,
    "dried basil": 0.21, "dried parsley": 0.20, "dried thyme": 0.27,
    "dried rosemary": 0.23, "cumin": 0.42, "paprika": 0.44,
    "chili powder": 0.50, "cayenne": 0.45, "black pepper": 0.45, "pepper": 0.45,
    "cinnamon": 0.42, "garlic powder": 0.52, "onion powder": 0.48,
}
_DENSITY_KEYS = sorted(_DENSITY, key=len, reverse=True)

# Fallback density when the food is unknown but clearly a liquid measure.
_UNKNOWN_DENSITY = None   # deliberately None → ask the user

# ── Count-based weights (g per item) ─────────────────────────────────────────
# USDA publishes per-item gram weights, but only for its own foods. Most
# matches in this app land on Canadian Nutrient File or CoFID rows, which carry
# no FDC id and therefore no household measures — so "2 large eggs" had nothing
# to resolve against and fell through to "weight needed" every time. These are
# the standard USDA item weights for the things recipes actually count.
_COUNT_WEIGHTS: dict[str, dict[str, float]] = {
    # One dried bay leaf is roughly 0.2 g. USDA portion lists sometimes expose
    # a 24 g package/household amount that must never be treated as one leaf.
    "bay leaf":     {"": 0.2},
    "cardamom pod": {"": 0.2},
    # Recipe chillies vary, but a 15 g small whole chilli is a materially safer
    # default than blocking the import or mistaking the number for grams.
    "chilli pepper": {"": 15},
    "chili pepper":  {"": 15},
    "green chilli":  {"": 15},
    "red chilli":    {"": 15},
    "green chili":   {"": 15},
    "red chili":     {"": 15},
    "egg":          {"jumbo": 63, "extra large": 56, "large": 50, "medium": 44, "small": 38, "": 50},
    "onion":        {"large": 150, "medium": 110, "small": 70, "": 110},
    "spring onion": {"": 15},
    "green onion":  {"": 15},
    "scallion":     {"": 15},
    "shallot":      {"": 25},
    "garlic clove": {"": 3},
    "carrot":       {"large": 72, "medium": 61, "small": 50, "": 61},
    "celery":       {"large": 64, "medium": 40, "small": 17, "": 40},
    "tomato":       {"large": 182, "medium": 123, "small": 91, "": 123},
    "potato":       {"large": 369, "medium": 213, "small": 170, "": 213},
    "banana":       {"large": 136, "medium": 118, "small": 101, "": 118},
    "apple":        {"large": 223, "medium": 182, "small": 149, "": 182},
    "lemon":        {"": 58},
    "lime":         {"": 67},
    "bell pepper":  {"large": 164, "medium": 119, "small": 74, "": 119},
    "courgette":    {"medium": 196, "": 196},
    "zucchini":     {"medium": 196, "": 196},
    "mushroom":     {"": 18},
    "rasher":       {"": 25},
    # US butter is sold in sticks; "1 stick" is half a cup, 113 g. Keyed with
    # the food name so "1 stick celery" is not caught by it.
    "stick butter": {"": 113},
    "slice bread":  {"": 28},
}
_COUNT_KEYS = sorted(_COUNT_WEIGHTS, key=len, reverse=True)


def count_weight(name: str, size: Optional[str]) -> Optional[tuple[float, bool]]:
    """
    Grams for one countable item. Returns (grams, size_was_given).

    A missing size adjective defaults to medium and is reported so the caller
    can flag it, per the spec.
    """
    hay = (name or "").lower()
    raw_unit = (size or "").lower()
    # "3 cloves garlic" is commonly parsed as name=garlic, unit=cloves. Keep
    # that convention without treating the spice called clove as garlic.
    if "garlic" in hay and re.search(r"\bcloves?\b", raw_unit):
        return 3.0, True
    if "bay" in hay and re.search(r"\blea(?:f|ves)\b", raw_unit):
        return 0.2, True
    # "3 cloves garlic" parses to name="garlic", unit="cloves" — the countable
    # thing is named by the unit, so search both.
    with_unit = f"{(size or '').lower()} {hay}".strip()
    for key in _COUNT_KEYS:
        # Include regular and common irregular plurals. A naïve `key + s`
        # misses tomatoes/potatoes; the old permissive suffix also failed on
        # leaf/leaves and could match unrelated words.
        plurals = {f"{key}s"}
        if key.endswith("chilli") or key.endswith("chili"):
            plurals.add(f"{key[:-1]}ies")
        if key.endswith("y"):
            plurals.add(f"{key[:-1]}ies")
        if key.endswith("leaf"):
            plurals.add(f"{key[:-4]}leaves")
        if key.endswith("o"):
            plurals.add(f"{key}es")
        forms = "|".join(re.escape(form) for form in (key, *sorted(plurals)))
        pat = rf"\b(?:{forms})\b"
        if re.search(pat, hay) or re.search(pat, with_unit):
            table = _COUNT_WEIGHTS[key]
            s = (size or "").strip().lower()
            if s in table:
                return table[s], bool(s) or set(table) == {""}
            for k, v in table.items():
                if k and k in s:
                    return v, True
            return table.get("", next(iter(table.values()))), set(table) == {""}
    return None


def item_weight_is_plausible(name: str, unit: Optional[str], grams: float) -> bool:
    """Reject clearly non-item USDA/cache portions before they become defaults.

    This is intentionally conservative. It does not try to decide whether a
    170 g versus 220 g potato is correct; it catches category errors such as a
    24 g package being interpreted as one dried leaf.
    """
    if not grams or grams <= 0 or grams > 5000:
        return False
    text = f"{name or ''} {unit or ''}".lower()
    bounds = (
        (r"\bbay\s+lea(?:f|ves)\b", 0.02, 2.0),
        (r"\bcardamom\s+pods?\b|\bpods?\s+cardamom\b", 0.03, 1.0),
        (r"\bpeppercorns?\b", 0.01, 1.0),
        (r"\bgarlic\s+cloves?\b|\bcloves?\s+garlic\b", 0.3, 15.0),
        (r"\b(?:herb\s+)?sprigs?\b", 0.05, 20.0),
    )
    for pattern, minimum, maximum in bounds:
        if re.search(pattern, text):
            return minimum <= grams <= maximum
    return True


def canonical_unit(unit: Optional[str]) -> Optional[str]:
    """Normalise a unit string to a canonical token, or None if not a unit."""
    if not unit:
        return None
    u = unit.strip().lower().rstrip(".")
    u = re.sub(r"\s+", " ", u)
    return _UNIT_ALIASES.get(u)


def density_for(name: str) -> Optional[float]:
    """Best-guess density (g/mL) from the ingredient name, or None."""
    n = (name or "").lower()
    for key in _DENSITY_KEYS:
        if key in n:
            return _DENSITY[key]
    return _UNKNOWN_DENSITY


def volume_ml(quantity: float, unit: str, locale: str = DEFAULT_LOCALE) -> Optional[float]:
    """Convert a volume quantity to millilitres for the given locale."""
    table = _VOLUME_ML.get(locale, _VOLUME_ML[DEFAULT_LOCALE])
    if unit == "ml":
        return quantity
    if unit == "l":
        return quantity * 1000.0
    if unit in table:
        return quantity * table[unit]
    return None


def is_volume_unit(unit: Optional[str]) -> bool:
    """Whether a stated unit is a household volume needing gram conversion."""
    return canonical_unit(unit) in _VOLUME_UNITS


def to_grams(
    quantity: Optional[float],
    unit: Optional[str],
    name: str,
    usda_portions: Optional[list[dict]] = None,
    locale: str = DEFAULT_LOCALE,
) -> tuple[Optional[float], str]:
    """
    Resolve a quantity to grams.

    Returns (grams, method) where method is one of:
      "mass"      — the unit was already a weight
      "usda"      — matched a USDA household measure for this specific food
      "density"   — volume converted using the density table
      "count"     — a count-based unit resolved from a USDA portion
      "unknown"   — could not resolve; caller must ask the user
    """
    if quantity is None or quantity <= 0:
        return None, "unknown"

    canon = canonical_unit(unit)

    # 0. Imprecise seasoning units resolve to a token amount, never a lookup.
    bare = (unit or "").strip().lower().rstrip("es").rstrip("s") if unit else ""
    for word, grams in IMPRECISE_G.items():
        if unit and word in (unit or "").strip().lower():
            return quantity * grams, "imprecise"

    # 1. Already a mass.
    if canon in _MASS_G:
        return quantity * _MASS_G[canon], "mass"

    # 2. For count-based ingredients, trusted culinary item weights win before
    # USDA portions. USDA can publish a package/household amount that looks
    # like one item (the source of "2 bay leaves = 48 g").
    if canon is None:
        hit = count_weight(name, unit)
        if hit is not None:
            grams, size_given = hit
            return quantity * grams, "count" if size_given else "count_default"

    # 3. A USDA household measure for this exact food wins for real volume
    # units. For a still-unresolved count, accept it only after validation.
    if usda_portions:
        grams = _match_usda_portion(unit, name, usda_portions)
        if grams is not None and (canon is not None or item_weight_is_plausible(name, unit, grams)):
            return quantity * grams, "usda" if canon else "count"

    # 4. Volume via the density table.
    if canon in _VOLUME_UNITS:
        ml = volume_ml(quantity, canon, locale)
        d  = density_for(name)
        if ml is not None and d is not None:
            return ml * d, "density"
        return None, "unknown"          # a real volume we cannot weigh — ask

    # 5. Count-based fallback (normally handled before USDA above; retained for
    # future unit aliases that canonicalise differently).
    hit = count_weight(name, unit)
    if hit is not None:
        grams, size_given = hit
        return quantity * grams, "count" if size_given else "count_default"

    return None, "unknown"


def _match_usda_portion(unit: Optional[str], name: str, portions: list[dict]) -> Optional[float]:
    """
    Find the gram weight of one `unit` of this food from USDA foodPortions.

    Each portion looks like {"modifier": "cup, chopped", "gramWeight": 160,
    "amount": 1, "measureUnit": {"name": "cup"}}.
    """
    want = canonical_unit(unit)
    raw  = (unit or "").strip().lower()
    best = None
    for p in portions:
        gram = p.get("gramWeight")
        amt  = p.get("amount") or 1
        if not gram or amt <= 0:
            continue
        per_unit = gram / amt
        measure  = ((p.get("measureUnit") or {}).get("name") or "").lower()
        modifier = (p.get("modifier") or "").lower()
        hay      = f"{measure} {modifier}".strip()

        if want and canonical_unit(measure) == want:
            return per_unit                      # exact unit match, best case
        if want and want in hay:
            best = best or per_unit
        # Count-based: "2 large eggs" → portion modifier contains "large"
        if not want and raw and raw.split()[0] in hay:
            best = best or per_unit
        # Bare count with no size word → prefer a "medium" portion
        if not want and not raw and "medium" in hay:
            best = best or per_unit
    return best
