"""Conservative, persistent micronutrient completion for newly saved foods.

Barcode/label data is authoritative for calories and macros but frequently has
no amino acids or speciality micronutrients.  This service fills *only blank*
non-core fields from a USDA Foundation/SR Legacy reference when both the food
name and per-100 g macro profile match closely.  Ambiguous or branded matches
are deliberately left incomplete rather than guessed.
"""
from datetime import datetime, timezone
from typing import Optional
import re

import httpx

from app.config import get_settings
from app.models.models import Ingredient
from app.services.usda import NUTRIENT_MAP, _extract_nutrients
from app.services.vision_ocr import _response_text


settings = get_settings()

CORE_FIELDS = {"calories", "protein_g", "fat_g", "carbs_g"}
STOP_WORDS = {
    "raw", "fresh", "cooked", "dry", "with", "without", "and", "or", "the",
    "of", "in", "from", "food", "foods", "organic", "frozen", "unsweetened",
    # "unsweetened" was already ignored but "sweetened" was not, so
    # "Dried Mangoes" could never match USDA's "Mangos, dried, sweetened".
    # Sweetening changes the macros, and _macro_error is what screens that.
    "sweetened", "natural", "style", "brand", "signature", "value", "select",
}

# Marketing words that appear in retail names but never in a USDA generic.
# Left out of STOP_WORDS because they are meaningful inside a *candidate*.
_NOISE = {"mini", "bites", "pieces", "chunks", "slices", "snack", "pack"}


def _stem(word: str) -> str:
    """Crude plural stem, applied identically to both sides of a comparison.

    The previous rule only stripped a trailing "s", so "mangoes" became
    "mangoe" while USDA's "mangos" became "mango" — the two could never match.
    """
    if len(word) > 4:
        if word.endswith("ies"):
            return word[:-3] + "y"          # berries -> berry
        if word.endswith("es") and not word.endswith(("ses", "ces")):
            return word[:-2]                # mangoes -> mango, tomatoes -> tomato
        if word.endswith("s"):
            return word[:-1]                # mangos -> mango
    return word


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return {_stem(w) for w in words if w not in STOP_WORDS and w not in _NOISE}


# Below these magnitudes (per 100 g) a difference is label rounding, not a
# mismatch: a label declaring "0 g fat" against a reference's 1.18 g is the
# same food. Dividing by the raw value turned that into 100% error and sank
# otherwise-perfect matches.
_ERROR_FLOOR = {"calories": 20.0, "protein_g": 5.0, "fat_g": 5.0, "carbs_g": 5.0}


def _search_query(text: str) -> str:
    """Strip punctuation USDA's search endpoint rejects.

    Its query parser treats brackets and similar characters as syntax, so a
    name like "Ground Bison, Extra Lean [Copy]" returns HTTP 400 — which the
    caller could only record as "lookup unavailable", making a malformed query
    look like a transient outage.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z\s]", " ", text)).strip()


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
        floor = _ERROR_FLOOR.get(field, 1.0)
        errors.append(abs(expected - actual) / max(expected, actual, floor))
    return sum(errors) / len(errors) if errors else 999.0


def _has_missing_micros(ingredient: Ingredient) -> bool:
    return any(
        field not in CORE_FIELDS and getattr(ingredient, field, None) is None
        for field in set(NUTRIENT_MAP.values())
    )


# ── Semantic confirmation ────────────────────────────────────────────────────
# Token overlap cannot tell a chocolate bar from a granola bar, and matching on
# macros alone is worse: four macros agreeing within 15% is common between
# entirely different foods. When the name heuristic is not confident enough on
# its own, ask the model whether the candidate is genuinely the same food.

_VERIFY_SYSTEM = """You match a retail food product to a generic USDA reference food. The reference's micronutrient values will be copied onto the product, so a wrong match silently corrupts nutrition data.

Answer with the number of a candidate ONLY if it is the same food.

Same food (accept): brand vs generic naming, packaging or marketing words, minor wording, an equivalent cut/variety.
Different food (reject): a different food type or base ingredient; a different preparation (raw vs cooked, dried vs fresh); a different form (bar vs cereal, powder vs liquid); a fortified or enriched version when the product is not, or a version with added nutrients the product does not have.

Similar calories and macros are NOT evidence of a match — unrelated foods often share a macro profile. Judge only by food identity.

Pay particular attention to form and base ingredient. A confectionery bar is not a granola or cereal bar. A cracker is not a bread. A drink is not a powder. If several candidates are close, choose the one matching the product's form and base ingredient, not the one sharing the most words.

If no candidate is clearly the same food, answer NONE. Prefer NONE when unsure.

Think briefly, then end your reply with a line of exactly this form:
ANSWER: <number>
or
ANSWER: NONE"""


async def _confirm_reference(ingredient: Ingredient, candidates: list[dict]) -> Optional[dict]:
    """Ask the model which candidate, if any, is genuinely the same food."""
    if not settings.ANTHROPIC_API_KEY or not candidates:
        return None

    label = ingredient.name if not ingredient.brand else f"{ingredient.brand} {ingredient.name}"
    listing = "\n".join(
        f"{i}. {c.get('description', '')}" for i, c in enumerate(candidates, 1)
    )
    payload = {
        "model":      settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 400,
        "system":     _VERIFY_SYSTEM,
        "messages":   [{"role": "user", "content": f"Product: {label}\n\nCandidates:\n{listing}"}],
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            answer = _response_text(resp.json())
    except (httpx.HTTPError, ValueError, KeyError):
        return None

    # Treat the reply as data: read only the final ANSWER line, so digits that
    # appear in the model's reasoning cannot be mistaken for its choice.
    match = re.search(r"ANSWER:\s*(\d+|NONE)\s*$", (answer or "").strip(), re.I | re.M)
    if not match or match.group(1).upper() == "NONE":
        return None
    index = int(match.group(1)) - 1
    return candidates[index] if 0 <= index < len(candidates) else None


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
                    "query": _search_query(query),
                    "pageSize": 12,
                    "dataType": ["Foundation", "SR Legacy"],
                },
            )
            search.raise_for_status()
            candidates = search.json().get("foods", [])

            input_tokens = _tokens(query)
            ranked = []
            plausible = []
            for candidate in candidates:
                description = candidate.get("description", "")
                candidate_tokens = _tokens(description)
                if not candidate_tokens:
                    continue
                shared = input_tokens & candidate_tokens
                # Neither containment direction works alone. A retail name
                # carries brand words the generic lacks ("Kirkland Signature,
                # Organic Dried Mangoes"); a USDA generic carries taxonomy the
                # retail name lacks ("Salad dressing, mayonnaise, regular").
                # Jaccard sinks the first, candidate-coverage sinks the second,
                # so accept either: the query saying everything the generic
                # says, OR the two agreeing overall.
                jaccard  = len(shared) / max(len(input_tokens | candidate_tokens), 1)
                coverage = len(shared) / len(candidate_tokens)
                overlap  = max(jaccard, coverage)
                # The heuristic tier needs at least two shared words so it can
                # never latch on via a single common token. A lone *distinctive*
                # word ("marinara") is real evidence though, so such candidates
                # still go forward for the model to judge.
                distinctive = {t for t in shared if len(t) >= 5}
                if not shared or (len(shared) < min(2, len(candidate_tokens)) and not distinctive):
                    continue
                heuristic_ok = len(shared) >= min(2, len(candidate_tokens))
                nutrients = _extract_nutrients(candidate)
                error = _macro_error(ingredient, nutrients)
                # Deliberately strict. Macro agreement does NOT identify a
                # food — a chocolate bar and a granola bar match on all four
                # macros — so the name has to carry the identification, and a
                # near miss must be left unfilled rather than guessed.
                if error > 0.15:
                    continue
                if overlap >= 0.70 and heuristic_ok:
                    ranked.append((overlap, error, candidate))
                else:
                    # Name evidence is too weak to accept on its own, but the
                    # macros are consistent — worth putting to the model.
                    plausible.append((len(shared), error, candidate))

            verified = False
            if ranked:
                _, _, selected = sorted(ranked, key=lambda row: (-row[0], row[1]))[0]
            else:
                shortlist = [c for _, _, c in sorted(plausible, key=lambda row: (-row[0], row[1]))[:8]]
                selected = await _confirm_reference(ingredient, shortlist)
                if selected is None:
                    ingredient.micronutrient_completion_status = "no_safe_reference"
                    return False
                verified = True

            fdc_id = selected["fdcId"]
            try:
                detail = await client.get(
                    f"{settings.USDA_BASE_URL}/food/{fdc_id}",
                    params={"api_key": settings.USDA_API_KEY},
                )
                detail.raise_for_status()
                reference = detail.json()
            except (httpx.HTTPError, ValueError):
                # Some USDA search-index entries 404 on /food/{id} — the record
                # is searchable but not individually retrievable. Losing an
                # otherwise-good match to that was making the row look like a
                # transient outage, so it retried forever. The search hit
                # already carries foodNutrients (it is what the macro gate is
                # scored against), so fall back to it. Fewer fields than the
                # full record, but a correct match beats none.
                reference = selected
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
    if not additions:
        ingredient.micronutrient_completion_status = "reference_no_new_fields"
    else:
        # Record HOW the match was made, so an AI-confirmed fill stays auditable.
        ingredient.micronutrient_completion_status = (
            "reference_completed_ai" if verified else "reference_completed"
        )
    return additions > 0
