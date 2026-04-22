/**
 * Recipes page — full list of saved recipes, searchable, with create + edit.
 */
import { useState, useEffect, useCallback } from "react";
import { recipesApi } from "../api/client";
import { Search, Plus, ChevronRight, Loader2, Utensils, Trash2, X } from "lucide-react";
import RecipeBuilderModal from "../components/RecipeBuilderModal";

export default function RecipesPage() {
  const [recipes, setRecipes]     = useState([]);
  const [loading, setLoading]     = useState(true);
  const [query, setQuery]         = useState("");
  const [showBuilder, setShowBuilder] = useState(false);
  const [editing, setEditing]     = useState(null);   // recipe object or null for new
  const [deleting, setDeleting]   = useState(null);

  const fetchRecipes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await recipesApi.list();
      setRecipes(res.data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchRecipes(); }, [fetchRecipes]);

  const filtered = query.length < 1
    ? recipes
    : recipes.filter(r =>
        r.name.toLowerCase().includes(query.toLowerCase())
      );

  const handleDelete = async (e, recipe) => {
    e.stopPropagation();
    if (!window.confirm(`Delete "${recipe.name}"?`)) return;
    setDeleting(recipe.id);
    try { await recipesApi.delete(recipe.id); fetchRecipes(); }
    catch { /* silent */ }
    finally { setDeleting(null); }
  };

  const openNew  = () => { setEditing(null); setShowBuilder(true); };
  const openEdit = (recipe) => { setEditing(recipe); setShowBuilder(true); };
  const onSaved  = () => { setShowBuilder(false); fetchRecipes(); };

  return (
    <div className="flex flex-col gap-3 pt-4">

      {/* ── Header row ── */}
      <div className="flex items-center justify-between">
        <p className="text-muted text-sm">{recipes.length} Recipe{recipes.length !== 1 ? "s" : ""}</p>
        <button onClick={openNew}
          className="flex items-center gap-1.5 btn-primary py-2 px-3 text-sm">
          <Plus size={14} /> New Recipe
        </button>
      </div>

      {/* ── Search ── */}
      <div className="relative w-full min-w-0 box-border">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search recipes…"
          className="input pl-8"
        />
        {query && (
          <button onClick={() => setQuery("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground">
            <X size={13} />
          </button>
        )}
      </div>

      {/* ── List ── */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={22} className="animate-spin text-muted" />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState query={query} onNew={openNew} />
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
                  ${i !== filtered.length - 1 ? "border-b border-surface-3" : ""}`}>
                {/* Icon */}
                <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center shrink-0">
                  <Utensils size={15} className="text-emerald-600" />
                </div>

                {/* Name + ingredient count */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{recipe.name}</p>
                  <p className="text-[11px] text-muted mt-0.5">
                    {recipe.ingredients.length} ingredient{recipe.ingredients.length !== 1 ? "s" : ""}
                    {recipe.serving_size_g ? ` · ${recipe.serving_size_g}g cooked` : ""}
                  </p>
                </div>

                {/* Macro chips */}
                <div className="flex flex-col items-end gap-0.5 shrink-0">
                  <span className="text-xs font-mono font-semibold" style={{ color: "#FF9500" }}>
                    {Math.round(per100)} <span className="text-muted font-normal text-[10px]">kcal/100g</span>
                  </span>
                  <span className="text-[11px] font-mono text-muted">
                    <span style={{ color: "#34C759" }}>{recipe.protein_g.toFixed(1)}P</span>
                    {" · "}
                    <span style={{ color: "#007AFF" }}>{recipe.carbs_g.toFixed(1)}C</span>
                    {" · "}
                    <span style={{ color: "#FF3B30" }}>{recipe.fat_g.toFixed(1)}F</span>
                  </span>
                </div>

                {/* Delete + chevron */}
                <div className="flex items-center gap-1 ml-1 shrink-0">
                  <button
                    onClick={e => handleDelete(e, recipe)}
                    disabled={deleting === recipe.id}
                    className="p-1.5 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red transition-colors opacity-0 group-hover:opacity-100">
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

      {/* ── Builder modal ── */}
      {showBuilder && (
        <RecipeBuilderModal
          recipe={editing}
          onClose={() => setShowBuilder(false)}
          onSaved={onSaved}
        />
      )}
    </div>
  );
}

function EmptyState({ query, onNew }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-surface-1 shadow-card flex items-center justify-center text-3xl">
        🍳
      </div>
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
