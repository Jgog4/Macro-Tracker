"""
USDA FoodData Central service.

Endpoints used:
  GET /fdc/v1/foods/search?query=<q>&pageSize=<n>&api_key=<key>
  GET /fdc/v1/food/<fdc_id>?api_key=<key>

Nutrient IDs (FoodData Central standard):
  1003 → Protein
  1004 → Total fat
  1005 → Carbohydrates
  1008 → Energy (kcal)
  1093 → Sodium
  1253 → Cholesterol
"""
import httpx
from typing import Optional

from app.config import get_settings
from app.models.models import Ingredient
from app.schemas.schemas import USDASearchResult

settings = get_settings()

NUTRIENT_MAP = {
    1008: "calories",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
    1093: "sodium_mg",
    1253: "cholesterol_mg",
    1258: "sat_fat_g",
    1257: "trans_fat_g",
    1079: "fiber_g",
    2000: "sugar_g",
}


def _extract_nutrients(food_data: dict) -> dict:
    result = {v: None for v in NUTRIENT_MAP.values()}
    nutrients = food_data.get("foodNutrients", [])
    for n in nutrients:
        # Different keys depending on whether this is a search result or detail
        nutrient_id = (
            n.get("nutrientId")
            or n.get("nutrient", {}).get("id")
            or (n.get("nutrientNumber") and int(n["nutrientNumber"]))
        )
        if nutrient_id in NUTRIENT_MAP:
            result[NUTRIENT_MAP[nutrient_id]] = n.get("value") or n.get("amount")
    return result


async def search_usda(query: str, limit: int = 10) -> list[USDASearchResult]:
    """Search USDA FoodData Central and return lightweight results."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.USDA_BASE_URL}/foods/search",
            params={
                "query":    query,
                "pageSize": limit,
                "api_key":  settings.USDA_API_KEY,
                "dataType": "Foundation,SR Legacy,Branded",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for food in data.get("foods", []):
        nutrients = _extract_nutrients(food)
        results.append(USDASearchResult(
            fdc_id=food["fdcId"],
            description=food.get("description", "Unknown"),
            brand_owner=food.get("brandOwner"),
            serving_size=food.get("servingSize"),
            serving_unit=food.get("servingSizeUnit"),
            **{k: v for k, v in nutrients.items() if k in USDASearchResult.model_fields},
        ))
    return results


async def import_usda_food(fdc_id: int) -> Ingredient:
    """Fetch full detail for one USDA item and return an unsaved Ingredient ORM object."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.USDA_BASE_URL}/food/{fdc_id}",
            params={"api_key": settings.USDA_API_KEY},
        )
        resp.raise_for_status()
        food = resp.json()

    nutrients = _extract_nutrients(food)
    serving_size   = food.get("servingSize")
    serving_unit   = food.get("servingSizeUnit", "g")
    serving_desc   = f"{serving_size} {serving_unit}" if serving_size else None
    # Convert to grams
    serving_g: Optional[float] = None
    if serving_size and serving_unit and serving_unit.lower() in ("g", "grams"):
        serving_g = float(serving_size)

    return Ingredient(
        source="usda",
        usda_fdc_id=fdc_id,
        name=food.get("description", "USDA Food"),
        brand=food.get("brandOwner") or food.get("brandName"),
        serving_size_desc=serving_desc,
        serving_size_g=serving_g,
        calories=nutrients.get("calories") or 0,
        protein_g=nutrients.get("protein_g") or 0,
        fat_g=nutrients.get("fat_g") or 0,
        sat_fat_g=nutrients.get("sat_fat_g"),
        trans_fat_g=nutrients.get("trans_fat_g"),
        carbs_g=nutrients.get("carbs_g") or 0,
        fiber_g=nutrients.get("fiber_g"),
        sugar_g=nutrients.get("sugar_g"),
        sodium_mg=nutrients.get("sodium_mg"),
        cholesterol_mg=nutrients.get("cholesterol_mg"),
    )
