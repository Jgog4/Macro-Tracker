"""
Vision / OCR service — Claude extracts nutrition data from an image.

Uses the Anthropic Messages API with vision support.
The model is given a strict JSON schema via the system prompt so the
response is always parseable without regex hacks.
"""
import json

import httpx

from app.config import get_settings
from app.schemas.schemas import VisionExtractResponse

settings = get_settings()

SYSTEM_PROMPT = """
You are a nutrition label reader. The user will send you an image of a nutrition
facts label, a restaurant menu, or a packaged food item.

Extract the following fields and return ONLY valid JSON — no markdown, no prose:

{
  "name":           "<product or dish name, or null>",
  "serving_size":   "<serving size as printed, or null>",
  "calories":       <number or null>,
  "protein_g":      <number or null>,
  "fat_g":          <number or null>,
  "carbs_g":        <number or null>,
  "sodium_mg":      <number or null>,
  "cholesterol_mg": <number or null>,
  "confidence":     <0.0-1.0 — how confident you are in the extraction>,
  "raw_text":       "<all text you could read from the label, or null>"
}

Rules:
- All numeric values must be floats (e.g. 12.0, not "12g").
- Omit units from numeric fields — only the number.
- If a value is clearly not present, use null.
- Do not invent values. If the image is unclear, lower confidence.
""".strip()


async def extract_nutrition_from_image(
    base64_image: str,
    mime_type: str = "image/jpeg",
) -> VisionExtractResponse:
    """
    Send a base64-encoded image to Claude and parse the structured response.
    Uses the Anthropic Messages API (https://api.anthropic.com/v1/messages).
    Falls back to an empty VisionExtractResponse with confidence=0 if the
    API key is not configured.
    """
    if not settings.ANTHROPIC_API_KEY:
        return VisionExtractResponse(confidence=0.0, raw_text="[Anthropic API key not configured]")

    payload = {
        "model": settings.ANTHROPIC_VISION_MODEL,
        "max_tokens": 512,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": mime_type,
                            "data":       base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Please extract the nutrition information from this image and return it as JSON.",
                    },
                ],
            }
        ],
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
        return VisionExtractResponse(**parsed)
    except (json.JSONDecodeError, TypeError, ValueError):
        return VisionExtractResponse(confidence=0.1, raw_text=raw_content)
