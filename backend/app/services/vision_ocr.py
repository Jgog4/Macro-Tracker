"""
Vision / OCR service — Claude extracts nutrition data from images.

Supports 1 or 2 images:
  - Image 1: nutrition facts label (required)
  - Image 2: front of package / ingredients list (optional, helps with product name)

Uses the Anthropic Messages API with vision support.
"""
import json
import re
from typing import Optional

import httpx

from app.config import get_settings
from app.schemas.schemas import VisionExtractResponse

settings = get_settings()

SYSTEM_PROMPT = """
You are a nutrition label reader. The user will send one or two images:
  - Image 1 (required): a nutrition facts label, restaurant menu, or packaged food item.
  - Image 2 (optional): the front of the package or ingredients list — use this to help identify the product name.

Extract ALL of the following fields and return ONLY valid JSON — no markdown, no prose:

{
  "name":           "<product or dish name, or null>",
  "serving_size":   "<serving size as printed on label, e.g. '1 cup (240mL)', or null>",
  "serving_size_g": <serving size in grams as a number, or null — parse '28g' → 28, '1 oz (28g)' → 28, '1 oz' → 28.35>,

  "calories":       <number or null>,

  "protein_g":      <number or null>,

  "fat_g":          <Total Fat in grams, or null>,
  "sat_fat_g":      <Saturated Fat in grams, or null>,
  "trans_fat_g":    <Trans Fat in grams, or null>,

  "carbs_g":        <Total Carbohydrate in grams, or null>,
  "fiber_g":        <Dietary Fiber in grams, or null>,
  "sugar_g":        <Total Sugars in grams, or null>,
  "added_sugar_g":  <Added Sugars in grams, or null>,

  "sodium_mg":      <Sodium in milligrams, or null>,
  "cholesterol_mg": <Cholesterol in milligrams, or null>,
  "potassium_mg":   <Potassium in milligrams, or null>,
  "calcium_mg":     <Calcium in milligrams — convert %DV if needed: 1%DV = 13mg, or null>,
  "iron_mg":        <Iron in milligrams — convert %DV if needed: 1%DV = 0.18mg, or null>,
  "vitamin_d_mcg":  <Vitamin D in micrograms — convert %DV if needed: 1%DV = 0.2mcg, or null>,

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
        "max_tokens": 900,
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
        result = VisionExtractResponse(**parsed)
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
