/**
 * Axios client — all requests prefixed with /api/v1.
 * Vite's dev proxy forwards to http://localhost:8000.
 */
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "/api/v1";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// ── Foods ────────────────────────────────────────────────────────────────────
export const foodsApi = {
  search:         (q, params = {})     => api.get("/foods/search",        { params: { q, ...params } }),
  getRestaurant:  (brand)              => api.get("/foods/restaurant",     { params: { brand } }),
  usdaSearch:     (q, limit = 10)      => api.get("/foods/usda/search",   { params: { q, limit } }),
  importUsda:     (fdc_id)             => api.post(`/foods/usda/${fdc_id}/import`),
  create:         (data)               => api.post("/foods/", data),
  get:            (id)                 => api.get(`/foods/${id}`),
  update:         (id, data)           => api.patch(`/foods/${id}`, data),
  delete:         (id)                 => api.delete(`/foods/${id}`),
};

// ── Meals ────────────────────────────────────────────────────────────────────
export const mealsApi = {
  logFood:        (data)               => api.post("/meals/", data),
  getToday:       ()                   => api.get("/meals/today"),
  getDay:         (dateStr)            => api.get(`/meals/day/${dateStr}`),
  updateItem:     (itemId, data)       => api.patch(`/meals/items/${itemId}`, data),
  deleteItem:     (itemId)             => api.delete(`/meals/items/${itemId}`),
  copyMeal:       (mealId, data)       => api.post(`/meals/${mealId}/copy`, data),
  setTarget:      (data)               => api.post("/meals/targets", data),
  getLatestTarget:()                   => api.get("/meals/targets/latest"),
};

// ── Recipes ──────────────────────────────────────────────────────────────────
export const recipesApi = {
  list:           ()                   => api.get("/recipes/"),
  search:         (q)                  => api.get("/recipes/", { params: { q } }),
  create:         (data)               => api.post("/recipes/", data),
  get:            (id)                 => api.get(`/recipes/${id}`),
  update:         (id, data)           => api.patch(`/recipes/${id}`, data),
  delete:         (id)                 => api.delete(`/recipes/${id}`),
};

// ── Vision ───────────────────────────────────────────────────────────────────
export const visionApi = {
  extract:        (formData)           => api.post("/vision/extract", formData, { headers: { "Content-Type": "multipart/form-data" } }),
  extractAndSave: (formData)           => api.post("/vision/extract-and-save", formData, { headers: { "Content-Type": "multipart/form-data" } }),
};

// ── Suggest ──────────────────────────────────────────────────────────────────
export const suggestApi = {
  suggest:        (params = {})        => api.get("/suggest/", { params }),
};

// ── API Keys ─────────────────────────────────────────────────────────────────
export const apiKeysApi = {
  list:           ()                   => api.get("/api-keys/"),
  create:         (name)               => api.post("/api-keys/", { name }),
  revoke:         (id)                 => api.delete(`/api-keys/${id}`),
};
