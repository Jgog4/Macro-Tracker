"""Conservative, persistent micronutrient completion for newly saved foods.

Barcode/label data is authoritative for calories and macros but frequently has
no amino acids or speciality micronutrients.  This service fills *only blank*
non-core fields from a USDA Foundation/SR Legacy reference when both the food
name and per-100 g macro profile match closely.  Ambiguous or branded matches
are deliberately left incomplete rather than guessed.
"""
from datetime import datetime, timezone
import re

import httpx

from app.config import get_settings
from app.models.models import Ingredient
from app.services.usda import NUTRIENT_MAP, _extract_nutrients


settings = get_settings()

CORE_FIELDS = {"calories", "protein_g", "fat_g", "carbs_g"}
STOP_WORDS = {
    "raw", "fresh", "cooked", "dry", "with", "without", "and", "or", "the",
    "of", "in", "from", "food", "foods", "organic", "frozen", "unsweetened",
}


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {
        word[:-1] if word.endswith("s") and len(word) > 4 else word
        for word in words if word not in STOP_WORDS
    }


def _macro_error(ingredient: Ingredient, candidate_nutrients: dict) -> float:
    """Mean relative error for the four label macros, normalised to 100 g."""
    base_g = ingredient.serving_size_g or 100.0
    errors = []
    for field in CORE_FIELDS:
        expected = (getattr(ingredient, field) or 0.0) * 100.0 / base_g
        actual = candidate_nutrients.get(field)
        if actual is None:
            return 999.0
        if max(expected, actual) < 1.0:
            continue
        errors.append(abs(expected - actual) / max(expected, actual, 1.0))
    return sum(errors) / len(errors) if errors else 999.0


def _has_missing_micros(ingredient: Ingredient) -> bool:
    return any(
        field not in CORE_FIELDS and getattr(ingredient, field, None) is None
        for field in set(NUTRIENT_MAP.values())
    )


async def complete_missing_micros(ingredient: Ingredient) -> bool:
    """Persist a high-confidence USDA reference profile; never raises on lookup failure."""
    # A direct USDA import already has the exact source record. Restaurant and
    # recipe proxy rows are composite foods, so a generic match would be unsafe.
    if ingredient.usda_fdc_id or ingredient.source == "restaurant":
        return False
    if not _has_missing_micros(ingredient) or len(_tokens(ingredient.name)) < 1:
        return False

    query = ingredient.name
    if ingredient.brand:
        # Avoid letting a manufacturer token reduce an otherwise exact generic
        # food-name match (e.g. "Brand Greek yogurt" → "Greek yogurt").
        brand_words = _tokens(ingredient.brand)
        query_words = [word for word in _tokens(ingredient.name) if word not in brand_words]
        if query_words:
            query = " ".join(query_words)

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            search = await client.post(
                f"{settings.USDA_BASE_URL}/foods/search",
                params={"api_key": settings.USDA_API_KEY},
                json={
                    "query": query,
                    "pageSize": 12,
                    "dataType": ["Foundation", "SR Legacy"],
                },
            )
            search.raise_for_status()
            candidates = search.json().get("foods", [])

            input_tokens = _tokens(query)
            ranked = []
            for candidate in candidates:
                description = candidate.get("description", "")
                candidate_tokens = _tokens(description)
                overlap = len(input_tokens & candidate_tokens) / max(len(input_tokens | candidate_tokens), 1)
                nutrients = _extract_nutrients(candidate)
                error = _macro_error(ingredient, nutrients)
                if overlap >= 0.70 and error <= 0.15:
                    ranked.append((overlap, error, candidate))

            if not ranked:
                ingredient.micronutrient_completion_status = "no_safe_reference"
                return False

            _, _, selected = sorted(ranked, key=lambda row: (-row[0], row[1]))[0]
            fdc_id = selected["fdcId"]
            detail = await client.get(
                f"{settings.USDA_BASE_URL}/food/{fdc_id}",
                params={"api_key": settings.USDA_API_KEY},
            )
            detail.raise_for_status()
            reference = detail.json()
    except (httpx.HTTPError, ValueError, KeyError):
        # Saving food must remain reliable if the optional completion lookup is
        # unavailable or the free USDA key is rate-limited.
        ingredient.micronutrient_completion_status = "lookup_unavailable"
        return False

    reference_nutrients = _extract_nutrients(reference)
    scale = (ingredient.serving_size_g or 100.0) / 100.0
    additions = 0
    for field, value in reference_nutrients.items():
        if field in CORE_FIELDS or value is None or getattr(ingredient, field, None) is not None:
            continue
        setattr(ingredient, field, round(float(value) * scale, 6))
        additions += 1

    ingredient.micronutrient_reference_fdc_id = fdc_id
    ingredient.micronutrient_reference_name = reference.get("description")
    ingredient.micronutrient_completed_at = datetime.now(timezone.utc)
    ingredient.micronutrient_completion_status = "reference_completed" if additions else "reference_no_new_fields"
    return additions > 0
