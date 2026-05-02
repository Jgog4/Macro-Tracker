/**
 * Library page — three tabs:
 *   Recipes      — saved multi-ingredient recipes (create / edit / delete)
 *   My Foods     — custom (camera scan) + personal (Cronometer import) ingredients
 *   Restaurants  — restaurant brand items, grouped by brand (log / delete)
 *
 * Tapping any food or recipe row opens FoodDetailModal for full nutrition info.
 */
import { useState, useEffect, useCallback } from "react";
import { foodsApi, recipesApi } from "../api/client";
import {
  Search, Plus, ChevronRight, ChevronDown, ChevronUp,
  Loader2, Utensils, Trash2, X, Pencil, Camera, User, Link, ImagePlus,
} from "lucide-react";
import RecipeBuilderModal  from "../components/RecipeBuilderModal";
import IngredientEditModal from "../components/IngredientEditModal";
import LogFoodModal        from "../components/LogFoodModal";
import FoodDetailModal     from "../components/FoodDetailModal";
import UrlFoodModal        from "../components/UrlFoodModal";
import VisionModal         from "../components/VisionModal";

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
  const [detail,      setDetail]      = useState(null); // recipe shown in detail

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

  // Build a pseudo-ingredient object so FoodDetailModal can render recipe macros
  const recipeAsFood = (r) => ({
    name:             r.name,
    source:           "personal",   // show "Personal" badge for recipes
    serving_size_g:   r.serving_size_g  ?? r.total_weight_g ?? null,
    serving_size_desc:r.serving_size_g
      ? `${r.serving_size_g} g`
      : r.total_weight_g
        ? `${r.total_weight_g} g total`
        : "full recipe",
    calories:  r.calories  ?? 0,
    protein_g: r.protein_g ?? 0,
    carbs_g:   r.carbs_g   ?? 0,
    fat_g:     r.fat_g     ?? 0,
    fiber_g:   r.fiber_g,
    sugar_g:   r.sugar_g,
  });

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
                onClick={() => setDetail(recipeAsFood(recipe))}
                className={`flex w-full items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors text-left group
                  ${i !== filtered.length - 1 ? "border-b border-surface-3" : ""}`}
              >
                <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center shrink-0">
                  <Utensils size={15} className="text-emerald-600" />
                </div>
                <div className="flex-1 min-w-0">
                  {/* No truncate — let name wrap */}
                  <p className="text-sm font-semibold text-foreground">{recipe.name}</p>
                  <p className="text-[11px] text-muted mt-0.5">
                    {Math.round(per100)} kcal/100g
                    {" · "}
                    <span style={{ color: "#34C759" }}>{recipe.protein_g.toFixed(1)}P</span>
                    {" · "}
                    <span style={{ color: "#007AFF" }}>{recipe.carbs_g.toFixed(1)}C</span>
                    {" · "}
                    <span style={{ color: "#FF3B30" }}>{recipe.fat_g.toFixed(1)}F</span>
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={e => { e.stopPropagation(); handleDelete(e, recipe); }}
                    disabled={deleting === recipe.id}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100"
                  >
                    {deleting === recipe.id
                      ? <Loader2 size={12} className="animate-spin" />
                      : <Trash2 size={12} />}
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); openEdit(recipe); }}
                    className="p-1.5 rounded-lg hover:bg-surface-3 text-muted transition-colors opacity-0 group-hover:opacity-100"
                    title="Edit recipe"
                  >
                    <Pencil size={12} />
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
      {detail && (
        <FoodDetailModal food={detail} onClose={() => setDetail(null)} />
      )}
    </div>
  );
}

// ── My Foods tab ──────────────────────────────────────────────────────────────
// Shows both source=custom (camera-scanned) and source=personal (Cronometer import).

function MyFoodsTab() {
  const [customFoods,   setCustomFoods]   = useState([]);
  const [personalFoods, setPersonalFoods] = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [query,         setQuery]         = useState("");
  const [logging,       setLogging]       = useState(null);
  const [editing,       setEditing]       = useState(null);
  const [deleting,      setDeleting]      = useState(null);
  const [detail,        setDetail]        = useState(null);
  const [showSheet,     setShowSheet]     = useState(false);
  const [showUrl,       setShowUrl]       = useState(false);
  const [showScan,      setShowScan]      = useState(false);

  const fetchFoods = useCallback(async () => {
    setLoading(true);
    try {
      // Backend source=custom returns BOTH custom + personal foods combined.
      // One call is enough — split client-side by food.source for icon/count display.
      const res = await foodsApi.list("custom");
      const all = res.data ?? [];
      setCustomFoods(all.filter(f => f.source === "custom"));
      setPersonalFoods(all.filter(f => f.source === "personal"));
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchFoods(); }, [fetchFoods]);

  // Merge + sort; food.source already contains "custom" or "personal"
  const allFoods = [
    ...customFoods,
    ...personalFoods,
  ].sort((a, b) => a.name.localeCompare(b.name));

  const filtered = query.length < 1
    ? allFoods
    : allFoods.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));

  const handleDelete = async (e, food) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${food.name}"?`)) return;
    setDeleting(food.id);
    try { await foodsApi.delete(food.id); fetchFoods(); }
    catch { /* silent */ }
    finally { setDeleting(null); }
  };

  const totalCount = customFoods.length + personalFoods.length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-muted text-sm">
          {totalCount} food{totalCount !== 1 ? "s" : ""}
          {personalFoods.length > 0 && (
            <span className="ml-1">
              · <span className="text-green-600">{personalFoods.length} personal</span>
              {customFoods.length > 0 && <span className="text-purple-500"> · {customFoods.length} scanned</span>}
            </span>
          )}
        </p>
        <button
          onClick={() => setShowSheet(true)}
          className="btn-primary py-2 px-3 text-sm flex items-center gap-1.5"
        >
          <Plus size={13} /> Add Food
        </button>
      </div>

      <SearchBox value={query} onChange={setQuery} placeholder="Search your foods…" />

      {loading ? (
        <Spinner />
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center py-16 gap-3 text-center">
          <span className="text-4xl">{query ? "🔍" : "📷"}</span>
          <p className="font-semibold text-foreground">
            {query ? `No foods matching "${query}"` : "No foods yet"}
          </p>
          <p className="text-muted text-sm">
            {query ? "Try a different search term" : "Foods you scan or import will appear here"}
          </p>
        </div>
      ) : (
        <div className="card-no-pad">
          {filtered.map((food, i) => (
            <div
              key={food.id}
              className={`group relative flex w-full items-center gap-2 px-4 py-3 hover:bg-surface-2 transition-colors cursor-pointer
                ${i !== filtered.length - 1 ? "border-b border-surface-3" : ""}`}
              onClick={() => setDetail(food)}
            >
              {/* Source icon */}
              {food.source === "custom" ? (
                <div className="w-8 h-8 rounded-xl bg-purple-50 flex items-center justify-center shrink-0">
                  <Camera size={14} className="text-purple-500" />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-xl bg-green-50 flex items-center justify-center shrink-0">
                  <User size={14} className="text-green-600" />
                </div>
              )}

              {/* Name + macros — full remaining width; pr keeps text clear of the buttons */}
              <div className="flex-1 min-w-0 pr-20">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <p className="text-sm font-semibold text-foreground">{food.name}</p>
                  {!food.serving_size_g && (
                    <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-amber-100 text-amber-700 shrink-0">no weight</span>
                  )}
                </div>
                <p className="text-[11px] text-muted mt-0.5">
                  <span style={{ color: "#FF9500" }}>{Math.round(food.calories)} kcal</span>
                  {food.serving_size_g ? ` · ${food.serving_size_g}g` : ""}
                  {" · "}
                  <span style={{ color: "#34C759" }}>{(food.protein_g || 0).toFixed(1)}P</span>
                  {" · "}
                  <span style={{ color: "#007AFF" }}>{(food.carbs_g || 0).toFixed(1)}C</span>
                  {" · "}
                  <span style={{ color: "#FF3B30" }}>{(food.fat_g || 0).toFixed(1)}F</span>
                </p>
              </div>

              {/* Actions — absolutely positioned so they don't consume row width */}
              <div
                className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-0.5"
                onClick={e => e.stopPropagation()}
              >
                <button
                  onClick={() => setLogging(food)}
                  className="w-8 h-8 flex items-center justify-center rounded-xl bg-accent-blue text-white hover:opacity-80 transition-opacity"
                  title="Log to meal"
                >
                  <Plus size={15} />
                </button>
                <button
                  onClick={() => setEditing(food)}
                  className="w-8 h-8 flex items-center justify-center rounded-xl text-muted hover:bg-surface-3 transition-colors"
                  title="Edit"
                >
                  <Pencil size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {logging && (
        <LogFoodModal
          food={logging}
          onClose={() => setLogging(null)}
          onLogged={() => setLogging(null)}
        />
      )}
      {editing && (
        <IngredientEditModal
          ingredient={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchFoods(); }}
        />
      )}
      {detail && (
        <FoodDetailModal
          food={detail}
          onClose={() => setDetail(null)}
          onLog={() => { setDetail(null); setLogging(detail); }}
        />
      )}

      {/* ── Add Food action sheet ── */}
      {showSheet && (
        <div
          className="fixed inset-0 flex flex-col justify-end"
          style={{ zIndex: 9998, backgroundColor: "rgba(0,0,0,0.4)" }}
          onClick={() => setShowSheet(false)}
        >
          <div
            className="bg-white rounded-t-2xl px-4 pt-4 pb-8 flex flex-col gap-2"
            onClick={e => e.stopPropagation()}
          >
            <div className="w-10 h-1 bg-surface-3 rounded-full mx-auto mb-2" />
            <p className="text-xs font-semibold text-muted uppercase tracking-wide px-1 mb-1">Add to My Foods</p>

            <button
              onClick={() => { setShowSheet(false); setShowUrl(true); }}
              className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-surface-2 transition-colors text-left"
            >
              <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center shrink-0">
                <Link size={16} className="text-accent-blue" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Add from Link</p>
                <p className="text-[11px] text-muted">Paste a recipe URL — AI estimates the nutrition</p>
              </div>
            </button>

            <button
              onClick={() => { setShowSheet(false); setShowScan(true); }}
              className="flex items-center gap-3 px-4 py-3 rounded-xl hover:bg-surface-2 transition-colors text-left"
            >
              <div className="w-9 h-9 rounded-xl bg-purple-50 flex items-center justify-center shrink-0">
                <ImagePlus size={16} className="text-accent-purple" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Upload Screenshot</p>
                <p className="text-[11px] text-muted">Photo of an ingredient list — AI estimates the nutrition</p>
              </div>
            </button>

            <button
              onClick={() => setShowSheet(false)}
              className="mt-1 py-3 rounded-xl text-sm font-semibold text-muted hover:bg-surface-2 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {showUrl && (
        <UrlFoodModal
          onClose={() => setShowUrl(false)}
          onSaved={() => { setShowUrl(false); fetchFoods(); }}
        />
      )}
      {showScan && (
        <VisionModal
          mode="estimate"
          onClose={() => setShowScan(false)}
          onSaved={() => { setShowScan(false); fetchFoods(); }}
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
  const [query,      setQuery]      = useState("");
  const [logging,    setLogging]    = useState(null);
  const [deleting,   setDeleting]   = useState(null);
  const [detail,     setDetail]     = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await foodsApi.getRestaurant();
        setFoods(res.data);
        const brands = [...new Set(res.data.map(f => f.brand).filter(Boolean))];
        if (brands.length) setOpenBrands({ [brands[0]]: true });
      } catch { /* silent */ }
      finally { setLoading(false); }
    })();
  }, []);

  const filtered = query.length < 1
    ? foods
    : foods.filter(f =>
        f.name.toLowerCase().includes(query.toLowerCase()) ||
        (f.brand || "").toLowerCase().includes(query.toLowerCase())
      );

  const grouped = filtered.reduce((acc, food) => {
    const b = food.brand || "Other";
    if (!acc[b]) acc[b] = [];
    acc[b].push(food);
    return acc;
  }, {});
  const brands = Object.keys(grouped).sort();

  const toggleBrand = (brand) =>
    setOpenBrands(s => ({ ...s, [brand]: !s[brand] }));

  const handleDelete = async (e, food) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${food.name}" from your library?`)) return;
    setDeleting(food.id);
    try {
      await foodsApi.delete(food.id);
      setFoods(f => f.filter(x => x.id !== food.id));
    } catch { /* silent */ }
    finally { setDeleting(null); }
  };

  if (loading) return <Spinner />;

  if (brands.length === 0 && !query) {
    return (
      <div className="flex flex-col items-center py-16 gap-3 text-center">
        <span className="text-4xl">🍽️</span>
        <p className="font-semibold text-foreground">No restaurant items yet</p>
        <p className="text-muted text-sm">
          Search for Chipotle, Cactus Club, Pokerrito, and others when adding food
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted text-sm">
        {brands.length} restaurant{brands.length !== 1 ? "s" : ""} · {filtered.length} item{filtered.length !== 1 ? "s" : ""}
      </p>

      <SearchBox value={query} onChange={setQuery} placeholder="Search restaurants & items…" />

      {brands.length === 0 && query && (
        <div className="flex flex-col items-center py-12 gap-2 text-center">
          <span className="text-3xl">🔍</span>
          <p className="text-muted text-sm">No items matching "{query}"</p>
        </div>
      )}

      {brands.map(brand => {
        const items  = grouped[brand];
        const isOpen = !!openBrands[brand];

        return (
          <div key={brand} className="card-no-pad">
            <button
              onClick={() => toggleBrand(brand)}
              className="flex w-full items-center gap-3 px-4 py-3 hover:bg-surface-2 transition-colors"
            >
              <div className="w-9 h-9 rounded-xl bg-orange-50 flex items-center justify-center shrink-0">
                <span className="text-sm font-bold text-orange-500">{brand.charAt(0).toUpperCase()}</span>
              </div>
              <div className="flex-1 min-w-0 text-left">
                <p className="text-sm font-semibold text-foreground">{brand}</p>
                <p className="text-[11px] text-muted">{items.length} item{items.length !== 1 ? "s" : ""}</p>
              </div>
              {isOpen
                ? <ChevronUp size={14} className="text-muted shrink-0" />
                : <ChevronDown size={14} className="text-muted shrink-0" />}
            </button>

            {isOpen && (
              <div className="border-t border-surface-3">
                {items.map((food, i) => (
                  <div
                    key={food.id}
                    className={`group flex w-full items-center gap-2 px-4 py-2.5 hover:bg-surface-2 transition-colors cursor-pointer
                      ${i !== items.length - 1 ? "border-b border-surface-3" : ""}`}
                    onClick={() => setDetail(food)}
                  >
                    <div className="flex-1 min-w-0">
                      {/* Name wraps fully — no truncate */}
                      <p className="text-sm text-foreground">{food.name}</p>
                      <p className="text-[11px] text-muted mt-0.5">
                        <span style={{ color: "#FF9500" }}>{Math.round(food.calories)} kcal</span>
                        {food.serving_size_g ? ` · ${food.serving_size_g}g` : ""}
                        {" · "}
                        <span style={{ color: "#34C759" }}>{(food.protein_g || 0).toFixed(1)}P</span>
                        {" · "}
                        <span style={{ color: "#007AFF" }}>{(food.carbs_g || 0).toFixed(1)}C</span>
                        {" · "}
                        <span style={{ color: "#FF3B30" }}>{(food.fat_g || 0).toFixed(1)}F</span>
                      </p>
                    </div>
                    <div className="flex items-center gap-0.5 shrink-0" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => setLogging(food)}
                        className="w-8 h-8 flex items-center justify-center rounded-xl bg-accent-blue text-white hover:opacity-80 transition-opacity"
                        title="Log to meal"
                      >
                        <Plus size={15} />
                      </button>
                      <button
                        onClick={e => handleDelete(e, food)}
                        disabled={deleting === food.id}
                        className="w-8 h-8 flex items-center justify-center rounded-xl text-muted hover:bg-red-50 hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100"
                        title="Remove"
                      >
                        {deleting === food.id
                          ? <Loader2 size={12} className="animate-spin" />
                          : <Trash2 size={13} />}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {logging && (
        <LogFoodModal
          food={logging}
          onClose={() => setLogging(null)}
          onLogged={() => setLogging(null)}
        />
      )}
      {detail && (
        <FoodDetailModal
          food={detail}
          onClose={() => setDetail(null)}
          onLog={() => { setDetail(null); setLogging(detail); }}
        />
      )}
    </div>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function SearchBox({ value, onChange, placeholder }) {
  return (
    <div className="relative w-full min-w-0">
      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="input pl-8 w-full min-w-0"
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
