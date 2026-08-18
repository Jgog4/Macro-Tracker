/**
 * Last-used portions are a small per-device convenience cache. It deliberately
 * records only a successful diary entry, so opening or cancelling a food never
 * changes the next default.
 */
const STORAGE_KEY = "macro-tracker:last-food-portions:v1";

function portionKey(food) {
  if (!food) return null;
  if (food.recipe_id) return `recipe:${food.recipe_id}`;
  if (food.fdc_id) return `fdc:${food.fdc_id}`;
  if (food.id) return `food:${food.id}`;
  return null;
}

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

export function getLastFoodPortion(food) {
  const key = portionKey(food);
  return key ? readAll()[key] || null : null;
}

export function saveLastFoodPortion(food, portion) {
  const key = portionKey(food);
  if (!key || !portion?.quantity_g || portion.quantity_g <= 0) return;
  try {
    const all = readAll();
    all[key] = {
      unit: portion.unit || "g",
      amount: Number(portion.amount) || 1,
      quantity_g: Number(portion.quantity_g),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // Private browsing/storage restrictions should never block food logging.
  }
}
