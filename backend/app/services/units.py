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

# Fixed-weight units need no density.
_MASS_G = {"g": 1.0, "kg": 1000.0, "mg": 0.001, "oz": 28.3495, "lb": 453.592}

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
    "butter": 0.911, "margarine": 0.91,
    "milk": 1.03, "buttermilk": 1.03, "cream": 1.00, "yogurt": 1.03, "yoghurt": 1.03,
    "water": 1.0, "stock": 1.0, "broth": 1.0, "juice": 1.04, "vinegar": 1.01,
    "soy sauce": 1.15, "fish sauce": 1.20, "ketchup": 1.14,
    "mayonnaise": 0.91, "peanut butter": 1.08, "tahini": 1.05,
    "rice": 0.85, "oats": 0.41, "rolled oats": 0.41, "breadcrumbs": 0.43,
    "salt": 1.22, "kosher salt": 0.69, "baking powder": 0.90, "baking soda": 1.10,
}
_DENSITY_KEYS = sorted(_DENSITY, key=len, reverse=True)

# Fallback density when the food is unknown but clearly a liquid measure.
_UNKNOWN_DENSITY = None   # deliberately None → ask the user


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

    # 1. Already a mass.
    if canon in _MASS_G:
        return quantity * _MASS_G[canon], "mass"

    # 2. A USDA household measure for this exact food always wins — it is
    #    measured for the food's real packing density, not inferred from a class.
    if usda_portions:
        grams = _match_usda_portion(unit, name, usda_portions)
        if grams is not None:
            return quantity * grams, "usda" if canon else "count"

    # 3. Volume via the density table.
    if canon in ("tsp", "tbsp", "cup", "floz", "ml", "l"):
        ml = volume_ml(quantity, canon, locale)
        d  = density_for(name)
        if ml is not None and d is not None:
            return ml * d, "density"
        return None, "unknown"          # a real volume we cannot weigh — ask

    # 4. Count-based ("2 large eggs") with no USDA portion to lean on.
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
