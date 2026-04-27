"""
USDA FoodData Central service.

Endpoints used:
  GET /fdc/v1/foods/search?query=<q>&pageSize=<n>&api_key=<key>
  GET /fdc/v1/food/<fdc_id>?api_key=<key>

USDA FoodData Central Nutrient IDs used here:
  1003 → Protein (g)
  1004 → Total fat (g)
  1005 → Carbohydrates, by difference (g)
  1007 → Ash (g)
  1008 → Energy (kcal)
  1009 → Sugars, total (g)
  1010 → Sucrose (g)
  1011 → Glucose (g)
  1012 → Fructose (g)
  1013 → Lactose (g)
  1014 → Maltose (g)
  1015 → Galactose (g)
  1051 → Water (g)
  1057 → Caffeine (mg)
  1059 → Alcohol, ethyl (g)
  1072 → Fatty acids, total trans (g)
  1079 → Fiber, total dietary (g)
  1082 → Fiber, soluble (g)
  1084 → Fiber, insoluble (g)
  1085 → Fatty acids, total monounsaturated (g)
  1086 → Fatty acids, total polyunsaturated (g)
  1087 → Calcium, Ca (mg)
  1089 → Iron, Fe (mg)
  1090 → Magnesium, Mg (mg)
  1091 → Phosphorus, P (mg)
  1092 → Potassium, K (mg)
  1093 → Sodium, Na (mg)
  1095 → Zinc, Zn (mg)
  1096 → Chromium, Cr (mcg)
  1098 → Copper, Cu (mg)
  1099 → Fluoride, F (mcg)   ← stored as mg (/1000)
  1100 → Iodine, I (mcg)
  1101 → Manganese, Mn (mg)
  1102 → Molybdenum, Mo (mcg)
  1103 → Selenium, Se (mcg)
  1105 → Retinol (mcg)
  1106 → Vitamin A, RAE (mcg)
  1107 → Carotene, beta (mcg)
  1108 → Carotene, alpha (mcg)
  1109 → Vitamin E, alpha-tocopherol (mg)
  1120 → Cryptoxanthin, beta (mcg)
  1121 → Lycopene (mcg)
  1122 → Lutein + zeaxanthin (mcg)
  1123 → Tocopherol, beta (mg)
  1124 → Tocopherol, gamma (mg)
  1125 → Tocopherol, delta (mg)
  1162 → Vitamin C, total ascorbic acid (mg)
  1165 → Thiamin (mg)
  1166 → Riboflavin (mg)
  1167 → Niacin (mg)
  1170 → Pantothenic acid (mg)
  1175 → Vitamin B-6 (mg)
  1177 → Folate, total (mcg)
  1178 → Vitamin B-12 (mcg)
  1180 → Choline, total (mg)
  1183 → Vitamin K (phylloquinone) (mcg)
  1185 → Phytosterols (mg)
  1187 → Folate, DFE (mcg DFE)
  1253 → Cholesterol (mg)
  1257 → Fatty acids, total trans (g)  [alt ID]
  1258 → Fatty acids, total saturated (g)
  1269 → Fatty acids, 18:1 (g)         ← not used here
  1278 → Fatty acids, 18:3 n-3 (ALA) (g)
  1292 → Fatty acids, 18:2 n-6 (LA) (g)
  1316 → Fatty acids, 20:4 n-6 (AA) (g)
  1404 → Fatty acids, 20:5 n-3 (EPA) (g)
  1405 → Fatty acids, 22:6 n-3 (DHA) (g)
  1410 → Vitamin D (D2 + D3) (mcg)
  2000 → Sugars, total including NLEA (g)  [alt for 1009]

Amino acid IDs:
  1210 → Tryptophan (g)
  1211 → Threonine (g)
  1212 → Isoleucine (g)
  1213 → Leucine (g)
  1214 → Lysine (g)
  1215 → Methionine (g)
  1216 → Cystine (g)
  1217 → Phenylalanine (g)
  1218 → Tyrosine (g)
  1219 → Valine (g)
  1220 → Arginine (g)
  1221 → Histidine (g)
  1222 → Alanine (g)
  1223 → Aspartic acid (g)
  1224 → Glutamic acid (g)
  1225 → Glycine (g)
  1226 → Proline (g)
  1227 → Serine (g)
  1228 → Hydroxyproline (g)
  1229 → Biotin (mcg)                 [alt, some datasets]
"""
import httpx
from typing import Optional

from app.config import get_settings
from app.models.models import Ingredient
from app.schemas.schemas import USDASearchResult

settings = get_settings()

# Maps USDA nutrient ID → Ingredient field name
NUTRIENT_MAP: dict[int, str] = {
    # Core macros
    1008: "calories",
    1003: "protein_g",
    1004: "fat_g",
    1005: "carbs_g",
    1093: "sodium_mg",
    1253: "cholesterol_mg",
    1258: "sat_fat_g",
    1072: "trans_fat_g",
    1257: "trans_fat_g",        # alt ID (some datasets)
    1079: "fiber_g",
    1009: "sugar_g",
    2000: "sugar_g",            # alt ID
    1092: "potassium_mg",

    # Vitamins
    1106: "vitamin_a_mcg",      # RAE
    1162: "vitamin_c_mg",
    1410: "vitamin_d_mcg",      # D2+D3 mcg
    1109: "vitamin_e_mg",       # alpha-tocopherol
    1183: "vitamin_k_mcg",
    1165: "thiamine_mg",
    1166: "riboflavin_mg",
    1167: "niacin_mg",
    1170: "pantothenic_acid_mg",
    1175: "pyridoxine_mg",
    1178: "cobalamin_mcg",
    1229: "biotin_mcg",
    1187: "folate_mcg",         # DFE (preferred)
    1177: "folate_mcg",         # total folate (fallback)
    1180: "choline_mg",
    1105: "retinol_mcg",
    1108: "alpha_carotene_mcg",
    1107: "beta_carotene_mcg",
    1120: "beta_cryptoxanthin_mcg",
    1122: "lutein_zeaxanthin_mcg",
    1121: "lycopene_mcg",
    1123: "beta_tocopherol_mg",
    1124: "gamma_tocopherol_mg",
    1125: "delta_tocopherol_mg",

    # Minerals
    1087: "calcium_mg",
    1089: "iron_mg",
    1090: "magnesium_mg",
    1091: "phosphorus_mg",
    1095: "zinc_mg",
    1098: "copper_mg",
    1101: "manganese_mg",
    1103: "selenium_mcg",
    1096: "chromium_mcg",
    1100: "iodine_mcg",
    1102: "molybdenum_mcg",
    1099: "fluoride_mg",        # USDA gives mcg; we divide by 1000 below

    # Fatty acids
    1085: "monounsaturated_fat_g",
    1086: "polyunsaturated_fat_g",
    1278: "omega3_ala_g",
    1404: "omega3_epa_g",
    1405: "omega3_dha_g",
    1292: "omega6_la_g",
    1316: "omega6_aa_g",
    1185: "phytosterol_mg",

    # Carb details
    1082: "soluble_fiber_g",
    1084: "insoluble_fiber_g",
    1012: "fructose_g",
    1015: "galactose_g",
    1011: "glucose_g",
    1013: "lactose_g",
    1014: "maltose_g",
    1010: "sucrose_g",
    1057: "caffeine_mg",
    1051: "water_g",
    1007: "ash_g",
    1059: "alcohol_g",

    # Amino acids
    1210: "tryptophan_g",
    1211: "threonine_g",
    1212: "isoleucine_g",
    1213: "leucine_g",
    1214: "lysine_g",
    1215: "methionine_g",
    1216: "cystine_g",
    1217: "phenylalanine_g",
    1218: "tyrosine_g",
    1219: "valine_g",
    1220: "arginine_g",
    1221: "histidine_g",
    1222: "alanine_g",
    1223: "aspartic_acid_g",
    1224: "glutamic_acid_g",
    1225: "glycine_g",
    1226: "proline_g",
    1227: "serine_g",
    1228: "hydroxyproline_g",
}

# USDA reports fluoride in mcg but our field is in mg
_MCG_TO_MG_FIELDS = {"fluoride_mg"}


def _extract_nutrients(food_data: dict) -> dict:
    result: dict[str, Optional[float]] = {v: None for v in set(NUTRIENT_MAP.values())}
    nutrients = food_data.get("foodNutrients", [])
    for n in nutrients:
        nutrient_id = (
            n.get("nutrientId")
            or n.get("nutrient", {}).get("id")
            or (n.get("nutrientNumber") and int(n["nutrientNumber"]))
        )
        if nutrient_id in NUTRIENT_MAP:
            field = NUTRIENT_MAP[nutrient_id]
            value = n.get("value") or n.get("amount")
            if value is not None:
                if field in _MCG_TO_MG_FIELDS:
                    value = value / 1000.0   # mcg → mg
                # Don't overwrite a non-None value with a duplicate mapping
                if result.get(field) is None:
                    result[field] = value
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
    # Convert to grams — USDA uses several aliases
    serving_g: Optional[float] = None
    if serving_size and serving_unit:
        u = serving_unit.lower().strip()
        if u in ("g", "grm", "gram", "grams", "gr"):
            serving_g = float(serving_size)
        elif u in ("oz", "ounce", "ounces"):
            serving_g = round(float(serving_size) * 28.3495, 1)
        elif u in ("ml", "milliliter", "milliliters", "millilitre"):
            serving_g = float(serving_size)   # water-like density approximation

    # Build kwargs — only pass fields that exist on Ingredient
    from app.models.models import Ingredient as IngredientModel
    valid_cols = {c.key for c in IngredientModel.__table__.columns}
    nutrient_kwargs = {k: v for k, v in nutrients.items() if k in valid_cols and v is not None}

    return Ingredient(
        source="usda",
        usda_fdc_id=fdc_id,
        name=food.get("description", "USDA Food"),
        brand=food.get("brandOwner") or food.get("brandName"),
        serving_size_desc=serving_desc,
        serving_size_g=serving_g,
        **nutrient_kwargs,
    )
