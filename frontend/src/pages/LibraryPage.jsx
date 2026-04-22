/**
 * Library page — three tabs:
 *   Recipes      — saved multi-ingredient recipes (create / edit / delete)
 *   My Foods     — custom ingredients from photo scanner (edit / delete)
 *   Restaurants  — restaurant brand items, grouped by brand (delete)
 */
import { useState, useEffect, useCallback } from "react";
import { foodsApi, recipesApi } from "../api/client";
import {
  Search, Plus, ChevronRight, ChevronDown, ChevronUp,
  Loader2, Utensils, Trash2, X, Pencil, Camera,
} from "lucide-react";
import RecipeBuilderModal  from "../components/RecipeBuilderModal";
import IngredientEditModal from "../components/IngredientEditModal";

const TABS = ["Recipes", "My Foods", "Restaurants"];

// ── Root ──────────────────────────────────────────────────────────────────────

export default function LibraryPage() {
  const [tab, setTab] = useState("Recipes");

  return (
    <div className="flex flex-col gap-4 pt-4">
      {/* Segmented control */}
      <div className="flex gap-1 bg-surface-2 rounded-xl p-1">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-all
              ${tab === t
                ? "bg-white text-foreground shadow-card"
                : "text-muted hover:text-foreground"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Recipes"     && <RecipesTab />}
      {tab === "My Foods"    && <MyFoodsTab />}
      {tab === "Restaurants" && <RestaurantsTab />}
    </div>
  );
}

// ── Recipes tab ───────────────────────────────────────────────────────────────

function RecipesTab() {
  const [recipes,     setRecipes]     = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [query,       setQuery]       = useState("");
  const [showBuilder, setShowBuilder] = useState(false);
  const [editing,     setEditing]     = useState(null);
  const [deleting,    setDeleting]    = useState(null);

  const fetchRecipes = useCallback(async () => {
    setLoading(true);
    try { const res = await recipesApi.list(); setRecipes(res.data); }
    catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRecipes(); }, [fetchRecipes]);

  const filtered = query.length < 1
    ? recipes
    : recipes.filter(r => r.name.toLowerCase().includes(query.toLowerCase()));

  const handleDelete = async (e, recipe) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${recipe.name}"?`)) return;
    setDeleting(recipe.id);
    try { await recipesApi.delete(recipe.id); fetchRecipes(); }
    catch { /* silent */ }
    finally { setDeleting(null); }
  };

  const openEdit = (recipe) => { setEditing(recipe); setShowBuilder(true); };
  const openNew  = ()        => { setEditing(null);   setShowBuilder(true); };
  const onSaved  = ()        => { setShowBuilder(false); fetchRecipes(); };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-muted text-sm">{recipes.length} recipe{recipes.length !== 1 ? "s" : ""}</p>
        <button onClick={openNew} className="btn-primary py-2 px-3 text-sm flex items-center gap-1.5">
          <Plus size={13} /> New Recipe
        </button>
      </div>

      <SearchBox value={query} onChange={setQuery} placeholder="Search recipes…" />

      {loading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <EmptyRecipes query={query} onNew={openNew} />
      ) : (
        <div className="card-no-pad">
          {filtered.map((recipe, i) => {
            const per100 = recipe.serving_size_g
              ? (recipe.calories / recipe.serving_size_g * 100)
              : recipe.total_weight_g
                ? (recipe.calories / recipe.total_weight_g * 100)
                : recipe.calories;
            return (
              <button
                key={recipe.id}
                onClick={() => openEdit(recipe)}
                className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors text-left group
                  ${i !== filtered.length - 1 ? "border-b border-surface-3" : ""}`}
              >
                <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center shrink-0">
                  <Utensils size={15} className="text-emerald-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{recipe.name}</p>
                  <p className="text-[11px] text-muted mt-0.5">
                    {recipe.ingredients.length} ingredient{recipe.ingredients.length !== 1 ? "s" : ""}
                    {recipe.serving_size_g ? ` · ${recipe.serving_size_g}g cooked` : ""}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-0.5 shrink-0">
                  <span className="text-xs font-mono font-semibold" style={{ color: "#FF9500" }}>
                    {Math.round(per100)} <span className="text-muted font-normal text-[10px]">kcal/100g</span>
                  </span>
                  <MacroLine p={recipe.protein_g} c={recipe.carbs_g} f={recipe.fat_g} />
                </div>
                <div className="flex items-center gap-1 ml-1 shrink-0">
                  <button
                    onClick={e => handleDelete(e, recipe)}
                    disabled={deleting === recipe.id}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100"
                  >
                    {deleting === recipe.id
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Trash2 size={12} />}
                  </button>
                  <ChevronRight size={14} className="text-muted" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {showBuilder && (
        <RecipeBuilderModal recipe={editing} onClose={() => setShowBuilder(false)} onSaved={onSaved} />
      )}
    </div>
  );
}

// ── My Foods tab ──────────────────────────────────────────────────────────────

function MyFoodsTab() {
  const [foods,    setFoods]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [query,    setQuery]    = useState("");
  const [editing,  setEditing]  = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchFoods = useCallback(async () => {
    setLoading(true);
    try { const res = await foodsApi.list("custom"); setFoods(res.data); }
    catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchFoods(); }, [fetchFoods]);

  const filtered = query.length < 1
    ? foods
    : foods.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));

  const handleDelete = async (food) => {
    if (!window.confirm(`Delete "${food.name}"?`)) return;
    setDeleting(food.id);
    try { await foodsApi.delete(food.id); fetchFoods(); }
    catch { /* silent */ }
    finally { setDeleting(null); }
  };

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted text-sm">{foods.length} custom food{foods.length !== 1 ? "s" : ""}</p>

      <SearchBox value={query} onChange={setQuery} placeholder="Search your foods…" />

      {loading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center py-16 gap-3 text-center">
          <span className="text-4xl">📷</span>
          <p className="font-semibold text-foreground">
            {query ? `No foods matching "${query}"` : "No custom foods yet"}
          </p>
          <p className="text-muted text-sm">
            {query ? "Try a different search term" : "Foods you scan with the camera will appear here"}
          </p>
        </div>
      ) : (
        <div className="card-no-pad">
          {filtered.map((food, i) => (
            <div
              key={food.id}
              className={`group flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors
                ${i !== filtered.length - 1 ? "border-b border-surface-3" : ""}`}
            >
              <div className="w-9 h-9 rounded-xl bg-purple-50 flex items-center justify-center shrink-0">
                <Camera size={15} className="text-purple-500" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">{food.name}</p>
                <p className="text-[11px] text-muted mt-0.5">
                  {Math.round(food.calories)} kcal
                  {food.serving_size_g ? ` · per ${food.serving_size_g}g` : " · per 100g"}
                </p>
              </div>
              <div className="shrink-0">
                <MacroLine p={food.protein_g} c={food.carbs_g} f={food.fat_g} />
              </div>
              <div className="flex items-center gap-1 ml-1 shrink-0">
                <button
                  onClick={() => setEditing(food)}
                  className="p-1.5 rounded-lg hover:bg-surface-3 text-muted transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={() => handleDelete(food)}
                  disabled={deleting === food.id}
                  className="p-1.5 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100"
                >
                  {deleting === food.id
                    ? <Loader2 size={12} className="animate-spin" />
                    : <Trash2 size={12} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <IngredientEditModal
          ingredient={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchFoods(); }}
        />
      )}
    </div>
  );
}

// ── Restaurants tab ───────────────────────────────────────────────────────────

function RestaurantsTab() {
  const [foods,      setFoods]      = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [openBrands, setOpenBrands] = useState({});
  const [deleting,   setDeleting]   = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await foodsApi.getRestaurant();
        setFoods(res.data);
        // Default-open the first brand
        const brands = [...new Set(res.data.map(f => f.brand).filter(Boolean))];
        if (brands.length) setOpenBrands({ [brands[0]]: true });
      } catch { /* silent */ }
      finally { setLoading(false); }
    })();
  }, []);

  // Group by brand
  const grouped = foods.reduce((acc, food) => {
    const b = food.brand || "Other";
    if (!acc[b]) acc[b] = [];
    acc[b].push(food);
    return acc;
  }, {});
  const brands = Object.keys(grouped).sort();

  const toggleBrand = (brand) =>
    setOpenBrands(s => ({ ...s, [brand]: !s[brand] }));

  const handleDelete = async (food) => {
    if (!window.confirm(`Remove "${food.name}" from your library?`)) return;
    setDeleting(food.id);
    try {
      await foodsApi.delete(food.id);
      setFoods(f => f.filter(x => x.id !== food.id));
    } catch { /* silent */ }
    finally { setDeleting(null); }
  };

  if (loading) return <Spinner />;

  if (brands.length === 0) {
    return (
      <div className="flex flex-col items-center py-16 gap-3 text-center">
        <span className="text-4xl">🍽️</span>
        <p className="font-semibold text-foreground">No restaurant items yet</p>
        <p className="text-muted text-sm">
          Search for Chipotle, Cactus Club, and others when adding food
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted text-sm">
        {brands.length} restaurant{brands.length !== 1 ? "s" : ""} · {foods.length} item{foods.length !== 1 ? "s" : ""}
      </p>

      {brands.map(brand => {
        const items  = grouped[brand];
        const isOpen = !!openBrands[brand];

        return (
          <div key={brand} className="card-no-pad">
            {/* Brand header */}
            <button
              onClick={() => toggleBrand(brand)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors"
            >
              <div className="w-9 h-9 rounded-xl bg-orange-50 flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-orange-500">{brand.charAt(0).toUpperCase()}</span>
              </div>
              <div className="flex-1 text-left min-w-0">
                <p className="text-sm font-semibold text-foreground">{brand}</p>
                <p className="text-[11px] text-muted">{items.length} item{items.length !== 1 ? "s" : ""}</p>
              </div>
              {isOpen
                ? <ChevronUp size={14} className="text-muted shrink-0" />
                : <ChevronDown size={14} className="text-muted shrink-0" />}
            </button>

            {/* Item rows */}
            {isOpen && (
              <div className="border-t border-surface-3">
                {items.map((food, i) => (
                  <div
                    key={food.id}
                    className={`group flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2 transition-colors
                      ${i !== items.length - 1 ? "border-b border-surface-3" : ""}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground truncate">{food.name}</p>
                      <p className="text-[11px] text-muted mt-0.5">
                        {Math.round(food.calories)} kcal
                        {food.serving_size_g ? ` · ${food.serving_size_g}g` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <MacroLine p={food.protein_g} c={food.carbs_g} f={food.fat_g} />
                      <button
                        onClick={() => handleDelete(food)}
                        disabled={deleting === food.id}
                        className="p-1.5 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100"
                      >
                        {deleting === food.id
                          ? <Loader2 size={12} className="animate-spin" />
                          : <Trash2 size={12} />}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="input pl-8"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground"
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
}

function MacroLine({ p, c, f }) {
  return (
    <span className="text-[11px] font-mono">
      <span style={{ color: "#34C759" }}>{(p || 0).toFixed(1)}P</span>
      <span className="text-muted"> · </span>
      <span style={{ color: "#007AFF" }}>{(c || 0).toFixed(1)}C</span>
      <span className="text-muted"> · </span>
      <span style={{ color: "#FF3B30" }}>{(f || 0).toFixed(1)}F</span>
    </span>
  );
}

function Spinner() {
  return (
    <div className="flex justify-center py-16">
      <Loader2 size={22} className="animate-spin text-muted" />
    </div>
  );
}

function EmptyRecipes({ query, onNew }) {
  return (
    <div className="flex flex-col items-center py-16 gap-4 text-center">
      <span className="text-4xl">🍳</span>
      <div>
        <p className="font-semibold text-foreground">
          {query ? `No recipes matching "${query}"` : "No recipes yet"}
        </p>
        <p className="text-muted text-sm mt-1">
          {query ? "Try a different search term" : "Create your first recipe to get started"}
        </p>
      </div>
      {!query && (
        <button onClick={onNew} className="btn-primary flex items-center gap-2">
          <Plus size={14} /> Create Recipe
        </button>
      )}
    </div>
  );
}
