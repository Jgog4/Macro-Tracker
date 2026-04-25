"""
Vision / OCR service — Claude extracts or estimates nutrition data.

Modes:
  1. extract_nutrition_from_images  — reads a nutrition facts label (1–2 images)
  2. estimate_from_ingredient_images — estimates from a photo of an ingredient list
  3. analyze_recipe_url             — fetches a URL and estimates per-serving nutrition

Uses the Anthropic Messages API.
"""
import json
import re
from html.parser import HTMLParser
from typing import Optional

import httpx

from app.config import get_settings
from app.schemas.schemas import VisionExtractResponse

settings = get_settings()

SYSTEM_PROMPT = """
You are a nutrition label reader. The user will send one or two images:
  - Image 1 (required): a nutrition facts label, restaurant menu, or packaged food item.
  - Image 2 (optional): the front of the package or ingredients list — use this to help identify the product name.

Extract ALL visible nutrition fields and return ONLY valid JSON — no markdown, no prose.

Return this exact structure (use null for any field not present on the label):

{
  "name":           "<product or dish name, or null>",
  "serving_size":   "<serving size as printed, e.g. '1 cup (240mL)', or null>",
  "serving_size_g": <serving size in grams as a number, or null — parse '28g' → 28, '1 oz (28g)' → 28, '1 oz' → 28.35>,

  "calories":       <number or null>,

  "protein_g":      <number or null>,

  "fat_g":                  <Total Fat in grams, or null>,
  "sat_fat_g":              <Saturated Fat in grams, or null>,
  "trans_fat_g":            <Trans Fat in grams, or null>,
  "monounsaturated_fat_g":  <Monounsaturated Fat in grams, or null>,
  "polyunsaturated_fat_g":  <Polyunsaturated Fat in grams, or null>,
  "omega3_ala_g":           <ALA (Omega-3) in grams, or null>,
  "omega3_dha_g":           <DHA (Omega-3) in grams, or null>,
  "omega3_epa_g":           <EPA (Omega-3) in grams, or null>,

  "carbs_g":            <Total Carbohydrate in grams, or null>,
  "fiber_g":            <Dietary Fiber in grams, or null>,
  "soluble_fiber_g":    <Soluble Fiber in grams, or null>,
  "insoluble_fiber_g":  <Insoluble Fiber in grams, or null>,
  "sugar_g":            <Total Sugars in grams, or null>,
  "added_sugar_g":      <Added Sugars in grams, or null>,

  "sodium_mg":        <Sodium in milligrams, or null>,
  "cholesterol_mg":   <Cholesterol in milligrams, or null>,
  "potassium_mg":     <Potassium in milligrams, or null>,
  "calcium_mg":       <Calcium in milligrams — convert %DV if needed: 1%DV = 13mg, or null>,
  "iron_mg":          <Iron in milligrams — convert %DV if needed: 1%DV = 0.18mg, or null>,
  "vitamin_d_mcg":    <Vitamin D in micrograms — convert %DV if needed: 1%DV = 0.2mcg, or null>,
  "magnesium_mg":     <Magnesium in milligrams — convert %DV if needed: 1%DV = 4.2mg, or null>,
  "zinc_mg":          <Zinc in milligrams — convert %DV if needed: 1%DV = 0.11mg, or null>,
  "phosphorus_mg":    <Phosphorus in milligrams — convert %DV if needed: 1%DV = 7mg, or null>,
  "vitamin_a_mcg":    <Vitamin A in mcg RAE — convert %DV if needed: 1%DV = 9mcg, or null>,
  "vitamin_c_mg":     <Vitamin C in milligrams — convert %DV if needed: 1%DV = 0.9mg, or null>,
  "vitamin_e_mg":     <Vitamin E in milligrams — convert %DV if needed: 1%DV = 0.15mg, or null>,
  "vitamin_k_mcg":    <Vitamin K in micrograms — convert %DV if needed: 1%DV = 1.2mcg, or null>,
  "thiamine_mg":      <Thiamin / B1 in milligrams — convert %DV if needed: 1%DV = 0.012mg, or null>,
  "riboflavin_mg":    <Riboflavin / B2 in milligrams — convert %DV if needed: 1%DV = 0.013mg, or null>,
  "niacin_mg":        <Niacin / B3 in milligrams — convert %DV if needed: 1%DV = 0.16mg, or null>,
  "folate_mcg":       <Folate / Folic Acid in mcg DFE — convert %DV if needed: 1%DV = 4mcg, or null>,
  "cobalamin_mcg":    <Vitamin B12 in micrograms — convert %DV if needed: 1%DV = 0.024mcg, or null>,
  "caffeine_mg":      <Caffeine in milligrams, or null>,
  "alcohol_g":        <Alcohol in grams, or null>,

  "confidence":     <0.0–1.0 — how confident you are in the overall extraction>,
  "raw_text":       "<all text readable from the label, or null>"
}

Rules:
- All numeric values must be plain floats (e.g. 12.0, not "12g").
- Omit units — numbers only.
- serving_size_g must be in grams; convert from oz (1 oz = 28.35 g) if needed.
- If a value is not present on the label, use null. Do not invent values.
- If the label shows a % Daily Value for a mineral/vitamin instead of an absolute amount,
  convert using the factors listed above.
- If the image is blurry or a value is unclear, lower confidence accordingly.
- Only include fields that are PRINTED on the label — do not infer or estimate unlisted nutrients.
""".strip()


def _parse_serving_size_g(serving_size: Optional[str]) -> Optional[float]:
    """Fallback parser: extract grams from a serving size string if the model didn't."""
    if not serving_size:
        return None
    # Look for explicit grams: "28g", "150 g", "(150g)", etc.
    m = re.search(r'\(?\s*([\d.]+)\s*g\s*\)?', serving_size, re.IGNORECASE)
    if m:
        return float(m.group(1))
    # Ounces: "1 oz", "1.0oz"
    m = re.search(r'([\d.]+)\s*oz', serving_size, re.IGNORECASE)
    if m:
        return round(float(m.group(1)) * 28.35, 1)
    return None


async def extract_nutrition_from_images(
    base64_images: list[tuple[str, str]],   # list of (base64_data, mime_type)
) -> VisionExtractResponse:
    """
    Send 1–2 base64-encoded images to Claude and parse the structured nutrition response.
    Falls back to an empty VisionExtractResponse with confidence=0 if the
    API key is not configured.
    """
    if not settings.ANTHROPIC_API_KEY:
        return VisionExtractResponse(confidence=0.0, raw_text="[Anthropic API key not configured]")

    # Build message content blocks: images first, then instruction text
    content = []
    for b64_data, mime_type in base64_images:
        content.append({
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": mime_type,
                "data":       b64_data,
            },
        })
    content.append({
        "type": "text",
        "text": (
            "Please extract the nutrition information from the provided image(s) and return it as JSON."
            if len(base64_images) == 1
            else "Image 1 is the nutrition facts label. Image 2 is the front of package / ingredients list. "
                 "Use both to extract the nutrition information and return it as JSON."
        ),
    })

    payload = {
        "model":      settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 1500,   # increased to accommodate larger response
        "system":     SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": content}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
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
        data = resp.json()

    raw_content = data["content"][0]["text"].strip()

    # Strip markdown fences if present
    if raw_content.startswith("```"):
        raw_content = "\n".join(
            line for line in raw_content.splitlines()
            if not line.startswith("```")
        ).strip()

    try:
        parsed = json.loads(raw_content)
        # Filter to only known VisionExtractResponse fields to avoid validation errors
        known = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result = VisionExtractResponse(**filtered)
        # Fallback: parse serving_size_g from string if model didn't supply it
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return VisionExtractResponse(confidence=0.1, raw_text=raw_content)


# Backwards-compatible single-image wrapper
async def extract_nutrition_from_image(
    base64_image: str,
    mime_type:    str = "image/jpeg",
) -> VisionExtractResponse:
    return await extract_nutrition_from_images([(base64_image, mime_type)])


# ── Shared JSON-output schema used by estimate prompts ────────────────────────
_JSON_SCHEMA = """
Return ONLY valid JSON — no markdown, no prose. Use this exact structure
(null for any field you cannot estimate):

{
  "name":           "<food or recipe name>",
  "serving_size":   "<e.g. '1 serving', '1 bowl (350g)'>",
  "serving_size_g": <grams per serving as a number, or null>,
  "calories":       <kcal per serving>,
  "protein_g":      <g>, "fat_g": <g>, "carbs_g": <g>,
  "fiber_g":        <g or null>, "sugar_g":     <g or null>,
  "sat_fat_g":      <g or null>, "trans_fat_g": <g or null>,
  "cholesterol_mg": <mg or null>, "sodium_mg":  <mg or null>,
  "potassium_mg":   <mg or null>, "calcium_mg": <mg or null>,
  "iron_mg":        <mg or null>, "magnesium_mg": <mg or null>,
  "zinc_mg":        <mg or null>, "phosphorus_mg": <mg or null>,
  "vitamin_a_mcg":  <mcg or null>, "vitamin_c_mg": <mg or null>,
  "vitamin_d_mcg":  <mcg or null>, "vitamin_e_mg": <mg or null>,
  "vitamin_k_mcg":  <mcg or null>,
  "thiamine_mg":    <mg or null>, "riboflavin_mg": <mg or null>,
  "niacin_mg":      <mg or null>, "folate_mcg":   <mcg or null>,
  "cobalamin_mcg":  <mcg or null>,
  "monounsaturated_fat_g": <g or null>,
  "polyunsaturated_fat_g": <g or null>,
  "omega3_ala_g":   <g or null>, "omega3_epa_g": <g or null>,
  "omega3_dha_g":   <g or null>,
  "caffeine_mg":    <mg or null>, "alcohol_g": <g or null>,
  "confidence": <0.0–1.0>
}
"""

INGREDIENT_LIST_PROMPT = f"""
You are a nutrition analyst. The user has uploaded a photo of an ingredient list,
food package back, or meal tracking screenshot.

Examine the ingredients/components shown and ESTIMATE the nutrition profile
per serving (or per the total if no serving info is given). Use USDA data and
your knowledge of typical ingredient proportions to make your best estimate.

{_JSON_SCHEMA}

Important: You are estimating — not reading a label. Use best judgement.
If the image is ambiguous, still provide your best estimate with a lower confidence score.
""".strip()

RECIPE_URL_PROMPT = f"""
You are a nutrition analyst. The user has provided text content from a recipe webpage.

Read the ingredient list and estimated yield (servings), then calculate the
nutrition profile PER SERVING using USDA data and standard food composition tables.
If yield is not mentioned, assume 4 servings for a main dish, 2 for a side, 1 for a single item.

{_JSON_SCHEMA}

Important: Base your estimates on actual USDA / standard food composition data for
each ingredient. Be precise for the macros (calories, protein, carbs, fat) and
provide your best estimates for vitamins and minerals. Set confidence ≥ 0.7 if
you have a clear ingredient list.
""".strip()


# ── Shared helper: send text to Claude and parse JSON response ────────────────

async def _call_claude_text(system: str, user_message: str) -> VisionExtractResponse:
    """Send a text-only request to Claude and parse a VisionExtractResponse."""
    if not settings.ANTHROPIC_API_KEY:
        return VisionExtractResponse(confidence=0.0, raw_text="[Anthropic API key not configured]")

    payload = {
        "model":    settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 1800,
        "system":   system,
        "messages": [{"role": "user", "content": user_message}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
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
        data = resp.json()

    raw = data["content"][0]["text"].strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()

    try:
        parsed   = json.loads(raw)
        known    = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result   = VisionExtractResponse(**filtered)
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return VisionExtractResponse(confidence=0.1, raw_text=raw)


# ── Ingredient-list image estimation ─────────────────────────────────────────

async def estimate_from_ingredient_images(
    base64_images: list[tuple[str, str]],
) -> VisionExtractResponse:
    """
    Estimate nutrition from a photo of an ingredient list / package back /
    meal-tracking screenshot. Claude estimates rather than reads a label.
    """
    if not settings.ANTHROPIC_API_KEY:
        return VisionExtractResponse(confidence=0.0, raw_text="[Anthropic API key not configured]")

    content = []
    for b64_data, mime_type in base64_images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": b64_data},
        })
    content.append({
        "type": "text",
        "text": "Please estimate the nutrition profile based on the ingredients/food shown in this image.",
    })

    payload = {
        "model":      settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 1800,
        "system":     INGREDIENT_LIST_PROMPT,
        "messages":   [{"role": "user", "content": content}],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
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
        data = resp.json()

    raw = data["content"][0]["text"].strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()

    try:
        parsed   = json.loads(raw)
        known    = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result   = VisionExtractResponse(**filtered)
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (json.JSONDecodeError, TypeError, ValueError):
        return VisionExtractResponse(confidence=0.1, raw_text=raw)


# ── URL recipe analysis ───────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Minimal HTML → plain text stripper."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "iframe"}

    def __init__(self):
        super().__init__()
        self._skip   = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def get_text(self, max_chars: int = 6000) -> str:
        return "\n".join(self._chunks)[:max_chars]


def _extract_recipe_text(html: str, url: str) -> str:
    """
    Try to extract structured recipe JSON-LD first; fall back to plain text.
    Returns a concise text representation for Claude to analyse.
    """
    # 1. Look for JSON-LD Recipe schema
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE
    ):
        try:
            obj = json.loads(match.group(1))
            # Handle @graph arrays
            items = obj if isinstance(obj, list) else obj.get("@graph", [obj])
            for item in items:
                if isinstance(item, dict) and "Recipe" in str(item.get("@type", "")):
                    name        = item.get("name", "")
                    ingredients = item.get("recipeIngredient", [])
                    yield_      = item.get("recipeYield", "")
                    instructions = item.get("recipeInstructions", [])
                    inst_text   = ""
                    if isinstance(instructions, list):
                        inst_text = " ".join(
                            (i.get("text", "") if isinstance(i, dict) else str(i))
                            for i in instructions[:5]
                        )
                    return (
                        f"Recipe: {name}\n"
                        f"Yield: {yield_}\n"
                        f"Ingredients:\n" + "\n".join(f"- {i}" for i in ingredients) +
                        (f"\n\nInstructions (excerpt): {inst_text[:500]}" if inst_text else "")
                    )
        except (json.JSONDecodeError, TypeError):
            continue

    # 2. Fall back to plain text extraction
    extractor = _TextExtractor()
    extractor.feed(html)
    return f"URL: {url}\n\n" + extractor.get_text(max_chars=5000)


async def analyze_recipe_url(url: str, name: Optional[str] = None) -> VisionExtractResponse:
    """
    Fetch a recipe URL and estimate per-serving nutrition using Claude.
    Raises httpx.HTTPError if the URL is unreachable.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    recipe_text = _extract_recipe_text(html, url)
    user_msg    = (
        f"Please estimate the nutrition per serving for this recipe.\n\n{recipe_text}"
        + (f"\n\nFood name override: {name}" if name else "")
    )

    result = await _call_claude_text(RECIPE_URL_PROMPT, user_msg)
    # If the model didn't infer a name, use user-supplied one
    if name and not result.name:
        result.name = name
    return result
