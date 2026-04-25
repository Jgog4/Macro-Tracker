/**
 * Collapsible meal section — iOS-style white card with separator-divided rows.
 * Recipe items have a chevron to expand their sub-ingredient breakdown.
 */
import { useState, useRef } from "react";
import { format, parseISO } from "date-fns";
import {
  ChevronDown, ChevronUp, ChevronRight,
  Plus, Trash2, Utensils, Pencil, Check, X, BookmarkPlus, Copy, Loader2,
} from "lucide-react";
import { mealsApi, recipesApi } from "../api/client";
import CopyMealModal from "./CopyMealModal";

export default function MealSection({ meal, onAddToMeal, onRefresh }) {
  const [open, setOpen]             = useState(true);
  const [deleting, setDeleting]     = useState(null);
  const [editing, setEditing]       = useState(null);
  const [editQty, setEditQty]       = useState("");
  const [editMeal, setEditMeal]     = useState("");
  const [saving, setSaving]         = useState(null);
  const [savingRecipe, setSavingRecipe] = useState(false);
  const [recipePrompt, setRecipePrompt] = useState(false);
  const [recipeName, setRecipeName]     = useState("");
  const [showCopy, setShowCopy]         = useState(false);
  // Track which recipe items have their sub-ingredient panel expanded
  const [expandedItems, setExpandedItems] = useState({});
  const recipeInputRef = useRef();

  const time = meal.logged_at
    ? format(parseISO(meal.logged_at), "h:mm a")
    : null;

  const toggleItemExpand = (itemId) =>
    setExpandedItems(prev => ({ ...prev, [itemId]: !prev[itemId] }));

  const handleDelete = async (itemId) => {
    setDeleting(itemId);
    try { await mealsApi.deleteItem(itemId); onRefresh(); }
    catch (e) { console.error(e); }
    finally { setDeleting(null); }
  };

  const startEdit = (item) => {
    setEditing(item.id);
    setEditQty(String(item.quantity_g));
    setEditMeal(String(meal.meal_number));
  };
  const cancelEdit = () => { setEditing(null); setEditQty(""); setEditMeal(""); };

  const handleSaveEdit = async (itemId) => {
    const qty      = parseFloat(editQty);
    const mealNum  = parseInt(editMeal, 10);
    if (!qty || qty <= 0) return;
    setSaving(itemId);
    try {
      const payload = { quantity_g: qty };
      if (mealNum > 0 && mealNum !== meal.meal_number) payload.meal_number = mealNum;
      await mealsApi.updateItem(itemId, payload);
      setEditing(null);
      onRefresh();
    }
    catch (e) { console.error(e); }
    finally { setSaving(null); }
  };

  const handleSaveAsRecipe = async () => {
    if (!recipeName.trim()) return;
    setSavingRecipe(true);
    try {
      const ingredients = meal.items
        .filter(i => i.ingredient_id)
        .map(i => ({ ingredient_id: i.ingredient_id, quantity_g: i.quantity_g }));
      if (!ingredients.length) { alert("No individual ingredients to save."); return; }
      await recipesApi.create({ name: recipeName.trim(), ingredients });
      setRecipePrompt(false); setRecipeName("");
    } catch (e) { alert(e.response?.data?.detail || "Failed to save recipe"); }
    finally { setSavingRecipe(false); }
  };

  return (
    <div className="card-no-pad">
      {/* ── Header ── */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center shrink-0">
            <Utensils size={14} className="text-accent-blue" />
          </div>
          <div className="text-left min-w-0">
            <p className="text-sm font-semibold text-foreground">Meal {meal.meal_number}</p>
            <p className="text-[11px] text-muted">
              <span className="font-semibold font-mono" style={{ color: "#FF9500" }}>
                {meal.total_calories.toFixed(0)} kcal
              </span>
              <span className="mx-1">·</span>
              <span style={{ color: "#34C759" }}>{meal.total_protein_g.toFixed(1)}P</span>
              <span className="mx-1">·</span>
              <span style={{ color: "#007AFF" }}>{meal.total_carbs_g.toFixed(1)}C</span>
              <span className="mx-1">·</span>
              <span style={{ color: "#FF3B30" }}>{meal.total_fat_g.toFixed(1)}F</span>
              {time && <span className="text-muted"> · {time}</span>}
            </p>
          </div>
        </div>

        {open
          ? <ChevronUp size={16} className="text-muted shrink-0" />
          : <ChevronDown size={16} className="text-muted shrink-0" />}
      </button>

      {showCopy && (
        <CopyMealModal
          meal={meal}
          onClose={() => setShowCopy(false)}
          onCopied={() => { setShowCopy(false); onRefresh(); }}
        />
      )}

      {open && (
        <div className="border-t border-surface-3">
          {meal.items?.map(item => (
            <div key={item.id} className="border-b border-surface-3 last:border-0">

              {/* ── Edit mode ── */}
              {editing === item.id ? (
                <div className="flex flex-col gap-2 px-4 py-2.5">
                  <p className="text-sm font-medium text-foreground">{item.display_name}</p>
                  <div className="flex items-center gap-2">
                    {/* Quantity */}
                    <input
                      type="number"
                      value={editQty}
                      onChange={e => setEditQty(e.target.value)}
                      className="input w-20 py-1 px-2"
                      autoFocus min="0.5" step="0.5"
                      onKeyDown={e => {
                        if (e.key === "Enter") handleSaveEdit(item.id);
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                    <span className="text-xs text-muted">g</span>
                    {/* Meal number */}
                    <span className="text-xs text-muted ml-2">Meal</span>
                    <input
                      type="number"
                      value={editMeal}
                      onChange={e => setEditMeal(e.target.value)}
                      className="input w-14 py-1 px-2"
                      min="1" step="1"
                      onKeyDown={e => {
                        if (e.key === "Enter") handleSaveEdit(item.id);
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                    <div className="flex items-center gap-1 ml-auto">
                      <button onClick={() => handleSaveEdit(item.id)} disabled={saving === item.id}
                        className="p-1.5 rounded-lg bg-green-50 text-accent-green">
                        {saving === item.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                      </button>
                      <button onClick={cancelEdit} className="p-1.5 rounded-lg hover:bg-surface-3 text-muted">
                        <X size={13} />
                      </button>
                    </div>
                  </div>
                </div>

              ) : (
                /* ── Normal view ── */
                <>
                  <div className="group flex w-full px-4 py-2.5 hover:bg-surface-2 transition-colors">
                    {/* Expand chevron for recipe items */}
                    <div className="shrink-0 pt-0.5 mr-1">
                      {item.recipe_id && item.components?.length > 0 ? (
                        <button
                          onClick={() => toggleItemExpand(item.id)}
                          className="p-0.5 text-muted hover:text-accent-blue transition-colors"
                          aria-label="Toggle ingredients">
                          <ChevronRight
                            size={13}
                            className={`transition-transform ${expandedItems[item.id] ? "rotate-90" : ""}`}
                          />
                        </button>
                      ) : (
                        <span className="w-[17px] inline-block" />
                      )}
                    </div>

                    {/* Two-line content */}
                    <div className="flex-1 min-w-0">
                      {/* Line 1: full name, wraps freely */}
                      <p className="text-sm text-foreground leading-snug">{item.display_name}</p>
                      {/* Line 2: weight · kcal · macros + actions */}
                      <div className="flex items-center justify-between mt-0.5">
                        <p className="text-[11px] text-muted">
                          {item.quantity_g}g
                          <span className="mx-1">·</span>
                          <span style={{ color: "#FF9500" }}>{item.calories.toFixed(0)} kcal</span>
                          <span className="mx-1">·</span>
                          <span style={{ color: "#34C759" }}>{item.protein_g.toFixed(1)}P</span>
                          <span className="mx-1">·</span>
                          <span style={{ color: "#007AFF" }}>{item.carbs_g.toFixed(1)}C</span>
                          <span className="mx-1">·</span>
                          <span style={{ color: "#FF3B30" }}>{item.fat_g.toFixed(1)}F</span>
                          {item.recipe_id && item.components?.length > 0 && (
                            <span className="ml-1 text-[10px] text-muted/60">
                              · {item.components.length} ingredient{item.components.length !== 1 ? "s" : ""}
                            </span>
                          )}
                        </p>
                        <div className="flex items-center gap-0.5 shrink-0 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => startEdit(item)}
                            className="p-1 rounded-lg hover:bg-surface-3 text-muted">
                            <Pencil size={11} />
                          </button>
                          <button onClick={() => handleDelete(item.id)} disabled={deleting === item.id}
                            className="p-1 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red">
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* ── Sub-ingredient breakdown (recipe expand) ── */}
                  {item.recipe_id && expandedItems[item.id] && item.components?.length > 0 && (
                    <div className="bg-surface-2 border-t border-surface-3">
                      {item.components.map(comp => (
                        <div key={comp.id}
                          className="flex items-center justify-between px-4 py-1.5 border-b border-surface-3 last:border-0">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <span className="text-muted/40 text-xs shrink-0 select-none">└</span>
                            <p className="text-xs text-subtle truncate">{comp.ingredient_name}</p>
                          </div>
                          <p className="text-[11px] font-mono text-muted shrink-0 ml-2">
                            {comp.quantity_g.toFixed(1)}g
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}

          {/* Recipe name prompt */}
          {recipePrompt && (
            <div className="flex items-center gap-2 px-4 py-2.5 border-t border-surface-3 bg-blue-50">
              <input
                ref={recipeInputRef}
                value={recipeName}
                onChange={e => setRecipeName(e.target.value)}
                placeholder="Recipe name…"
                className="input flex-1 py-1.5 px-2"
                autoFocus
                onKeyDown={e => {
                  if (e.key === "Enter") handleSaveAsRecipe();
                  if (e.key === "Escape") { setRecipePrompt(false); setRecipeName(""); }
                }}
              />
              <button onClick={handleSaveAsRecipe} disabled={savingRecipe || !recipeName.trim()}
                className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1">
                {savingRecipe ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Save
              </button>
              <button onClick={() => { setRecipePrompt(false); setRecipeName(""); }}
                className="p-1 rounded-lg hover:bg-surface-3 text-muted"><X size={13} /></button>
            </div>
          )}

          {/* Footer actions */}
          <div className="flex border-t border-surface-3">
            <button onClick={onAddToMeal}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-medium text-accent-blue hover:bg-surface-2 transition-colors">
              <Plus size={13} /> Add food
            </button>
            {!recipePrompt && meal.items?.some(i => i.ingredient_id) && (
              <button
                onClick={() => { setRecipePrompt(true); setTimeout(() => recipeInputRef.current?.focus(), 50); }}
                className="flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted hover:text-accent-blue hover:bg-surface-2 transition-colors border-l border-surface-3">
                <BookmarkPlus size={13} /> Save recipe
              </button>
            )}
            <button
              onClick={() => setShowCopy(true)}
              className="flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-medium text-muted hover:text-accent-blue hover:bg-surface-2 transition-colors border-l border-surface-3">
              <Copy size={13} /> Copy
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

