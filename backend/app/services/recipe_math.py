"""Pure recipe nutrition calculations shared by every creation path."""


def compute_recipe_totals(ingredients_with_qty: list[tuple]) -> dict:
    """Sum ingredient nutrition, including reviewed cooking-fat retention."""
    totals = dict(calories=0.0, protein_g=0.0, fat_g=0.0, carbs_g=0.0,
                  sodium_mg=0.0, cholesterol_mg=0.0, total_weight_g=0.0)
    for entry in ingredients_with_qty:
        ing, qty_g = entry[0], entry[1]
        fat_retention = max(0.0, min(1.0, float(entry[2]))) if len(entry) > 2 else 1.0
        base_g = ing.serving_size_g or 100.0
        ratio = qty_g / base_g if base_g else 1.0
        original_fat = (ing.fat_g or 0) * ratio
        removed_fat = original_fat * (1.0 - fat_retention)
        totals["calories"] += max(0.0, (ing.calories or 0) * ratio - removed_fat * 9)
        totals["protein_g"] += (ing.protein_g or 0) * ratio
        totals["fat_g"] += original_fat * fat_retention
        totals["carbs_g"] += (ing.carbs_g or 0) * ratio
        totals["sodium_mg"] += (ing.sodium_mg or 0) * ratio
        totals["cholesterol_mg"] += (ing.cholesterol_mg or 0) * ratio
        totals["total_weight_g"] += qty_g
    return {key: round(value, 2) for key, value in totals.items()}
