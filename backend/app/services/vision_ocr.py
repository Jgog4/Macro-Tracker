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
You are a nutrition analyst. The user will send one or two images:
  - Image 1 (required): a nutrition facts label, restaurant menu, or packaged food item.
  - Image 2 (optional): the front of the package or ingredients list — use this to help identify the product name.

Your job is TWO-STEP:

STEP 1 — EXTRACT from the label (exact values only):
Read every number printed on the nutrition label and record it precisely.
If the label shows a % Daily Value instead of an absolute amount, convert using:
  Calcium 1%DV=13mg, Iron 1%DV=0.18mg, Vitamin D 1%DV=0.2mcg, Magnesium 1%DV=4.2mg,
  Zinc 1%DV=0.11mg, Phosphorus 1%DV=7mg, Vitamin A 1%DV=9mcg, Vitamin C 1%DV=0.9mg,
  Vitamin E 1%DV=0.15mg, Vitamin K 1%DV=1.2mcg, Thiamin 1%DV=0.012mg,
  Riboflavin 1%DV=0.013mg, Niacin 1%DV=0.16mg, Folate 1%DV=4mcg, B12 1%DV=0.024mcg,
  Potassium 1%DV=47mg.

STEP 2 — ESTIMATE missing nutrients:
For any nutrient field NOT shown on the label, estimate a reasonable value based on:
  • The food name and product type
  • The ingredient list (if visible)
  • The extracted macros (calories, protein, fat, carbs)
  • USDA nutritional composition data for similar foods
Use 0 (not null) only if the nutrient is truly absent in this food type (e.g. Vitamin C in plain meat).
Use null only if you genuinely cannot estimate (ambiguous food with no name or context).

Return ONLY valid JSON — no markdown, no prose:

{
  "name":           "<product or dish name, or null>",
  "serving_size":   "<serving size as printed, e.g. '1 bar (14g)', or null>",
  "serving_size_g": <serving size in grams — parse '14g'→14, '1 oz (28g)'→28, '1 oz'→28.35, or null>,

  "calories":       <number>,

  "protein_g":      <number>,

  "fat_g":                  <Total Fat in grams>,
  "sat_fat_g":              <Saturated Fat in grams>,
  "trans_fat_g":            <Trans Fat in grams>,
  "monounsaturated_fat_g":  <Monounsaturated Fat — estimate if not on label>,
  "polyunsaturated_fat_g":  <Polyunsaturated Fat — estimate if not on label>,
  "omega3_ala_g":           <ALA Omega-3 — estimate if not on label>,
  "omega3_dha_g":           <DHA Omega-3 — estimate if not on label, 0 for plant foods>,
  "omega3_epa_g":           <EPA Omega-3 — estimate if not on label, 0 for plant foods>,

  "carbs_g":            <Total Carbohydrate>,
  "fiber_g":            <Dietary Fiber>,
  "soluble_fiber_g":    <Soluble Fiber — estimate if not on label>,
  "insoluble_fiber_g":  <Insoluble Fiber — estimate if not on label>,
  "sugar_g":            <Total Sugars>,
  "added_sugar_g":      <Added Sugars>,

  "sodium_mg":        <Sodium>,
  "cholesterol_mg":   <Cholesterol>,
  "potassium_mg":     <Potassium — estimate from label %DV or food type if not shown>,
  "calcium_mg":       <Calcium>,
  "iron_mg":          <Iron>,
  "vitamin_d_mcg":    <Vitamin D>,
  "magnesium_mg":     <Magnesium — estimate if not on label>,
  "zinc_mg":          <Zinc — estimate if not on label>,
  "phosphorus_mg":    <Phosphorus — estimate if not on label>,
  "vitamin_a_mcg":    <Vitamin A>,
  "vitamin_c_mg":     <Vitamin C>,
  "vitamin_e_mg":     <Vitamin E — estimate if not on label>,
  "vitamin_k_mcg":    <Vitamin K — estimate if not on label>,
  "thiamine_mg":      <Thiamin / B1 — estimate if not on label>,
  "riboflavin_mg":    <Riboflavin / B2 — estimate if not on label>,
  "niacin_mg":        <Niacin / B3 — estimate if not on label>,
  "folate_mcg":       <Folate — estimate if not on label>,
  "cobalamin_mcg":    <Vitamin B12 — estimate if not on label>,
  "caffeine_mg":      <Caffeine — 0 if not a caffeinated product>,
  "alcohol_g":        <Alcohol — 0 if not an alcoholic product>,

  "confidence":     <0.85–1.0 if label is clear; 0.6–0.85 if label is partial or blurry>,
  "raw_text":       "<all text readable from the label>"
}

Rules:
- All numeric values must be plain floats (e.g. 12.0, not "12g"). Omit units.
- serving_size_g must be in grams; convert oz→g (1 oz = 28.35 g) if needed.
- For label-extracted values: use the exact printed number.
- For estimated values: use your best knowledge; don't use null when you can estimate.
- If the image is blurry or unreadable, lower confidence and still estimate what you can.
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
        "max_tokens": 3000,
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

    try:
        parsed  = _extract_json_from_text(raw_content)
        known   = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result  = VisionExtractResponse(**filtered)
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (ValueError, TypeError):
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

def _extract_json_from_text(raw: str) -> dict:
    """
    Robustly extract a JSON object from a Claude response that may include
    surrounding prose or markdown fences. Raises ValueError if no JSON found.
    """
    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if "```" in raw:
        raw = "\n".join(
            line for line in raw.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    # Try parsing the whole string first (fast path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find the outermost { ... } block
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in response: {raw[:300]}")


async def _call_claude_text(system: str, user_message: str) -> VisionExtractResponse:
    """Send a text-only request to Claude and parse a VisionExtractResponse."""
    if not settings.ANTHROPIC_API_KEY:
        return VisionExtractResponse(confidence=0.0, raw_text="[Anthropic API key not configured]")

    payload = {
        "model":      settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 3000,
        "system":     system,
        "messages":   [{"role": "user", "content": user_message}],
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
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

    try:
        parsed   = _extract_json_from_text(raw)
        known    = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result   = VisionExtractResponse(**filtered)
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (ValueError, TypeError) as exc:
        # Return a sentinel: confidence=0.0, raw_text preserved for debugging
        return VisionExtractResponse(confidence=0.0, raw_text=str(exc)[:500])


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

    try:
        parsed   = _extract_json_from_text(raw)
        known    = set(VisionExtractResponse.model_fields.keys())
        filtered = {k: v for k, v in parsed.items() if k in known}
        result   = VisionExtractResponse(**filtered)
        if result.serving_size_g is None and result.serving_size:
            result.serving_size_g = _parse_serving_size_g(result.serving_size)
        return result
    except (ValueError, TypeError) as exc:
        return VisionExtractResponse(confidence=0.0, raw_text=str(exc)[:500])


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
