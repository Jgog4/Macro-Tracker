/**
 * Collapsible meal section — "Meal 1", "Meal 2", etc.
 * Shows meal total macros in header, expandable item list.
 * Supports inline quantity editing and saving the meal as a named Recipe.
 */
import { useState, useRef } from "react";
import { format, parseISO } from "date-fns";
import { ChevronDown, ChevronUp, Plus, Trash2, Utensils, Pencil, Check, X, BookmarkPlus, Loader2 } from "lucide-react";
import { mealsApi, recipesApi } from "../api/client";

export default function MealSection({ meal, onAddToMeal, onRefresh }) {
  const [open, setOpen]         = useState(true);
  const [deleting, setDeleting] = useState(null);
  const [editing, setEditing]   = useState(null);   // item id being edited
  const [editQty, setEditQty]   = useState("");
  const [saving, setSaving]     = useState(null);
  const [savingRecipe, setSavingRecipe] = useState(false);
  const [recipePrompt, setRecipePrompt] = useState(false);
  const [recipeName, setRecipeName]     = useState("");
  const recipeInputRef = useRef();

  const time = meal.logged_at
    ? format(parseISO(meal.logged_at), "h:mm a")
    : null;

  const handleDelete = async (itemId) => {
    setDeleting(itemId);
    try {
      await mealsApi.deleteItem(itemId);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setDeleting(null);
    }
  };

  const startEdit = (item) => {
    setEditing(item.id);
    setEditQty(String(item.quantity_g));
  };

  const cancelEdit = () => {
    setEditing(null);
    setEditQty("");
  };

  const handleSaveEdit = async (itemId) => {
    const qty = parseFloat(editQty);
    if (!qty || qty <= 0) return;
    setSaving(itemId);
    try {
      await mealsApi.updateItem(itemId, { quantity_g: qty });
      setEditing(null);
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(null);
    }
  };

  const handleSaveAsRecipe = async () => {
    if (!recipeName.trim()) return;
    setSavingRecipe(true);
    try {
      // Only include items that have an ingredient_id (not recipe items)
      const ingredients = meal.items
        .filter(i => i.ingredient_id)
        .map(i => ({ ingredient_id: i.ingredient_id, quantity_g: i.quantity_g }));
      if (ingredients.length === 0) {
        alert("No individual ingredients found in this meal to save as a recipe.");
        return;
      }
      await recipesApi.create({ name: recipeName.trim(), ingredients });
      setRecipePrompt(false);
      setRecipeName("");
    } catch (e) {
      console.error(e);
      alert(e.response?.data?.detail || "Failed to save recipe");
    } finally {
      setSavingRecipe(false);
    }
  };

  return (
    <div className="card flex flex-col gap-0 p-0 overflow-hidden">
      {/* ── Meal header ─────────────────────────────────────── */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-surface-3 flex items-center justify-center">
            <Utensils size={14} className="text-accent-blue" />
          </div>
          <div className="text-left">
            <p className="text-sm font-semibold">Meal {meal.meal_number}</p>
            {time && <p className="text-[11px] text-muted">{time}</p>}
          </div>
        </div>

        {/* Totals */}
        <div className="flex items-center gap-4 mr-2">
          <MacroChip value={meal.total_calories}  unit="kcal" color="text-accent-orange" />
          <MacroChip value={meal.total_protein_g} unit="P"    color="text-accent-green" />
          <MacroChip value={meal.total_carbs_g}   unit="C"    color="text-accent-blue" />
          <MacroChip value={meal.total_fat_g}     unit="F"    color="text-accent-red" />
        </div>

        {open ? <ChevronUp size={16} className="text-muted shrink-0" />
               : <ChevronDown size={16} className="text-muted shrink-0" />}
      </button>

      {/* ── Item list ────────────────────────────────────────── */}
      {open && (
        <div className="border-t border-border">
          {meal.items?.map(item => (
            <div key={item.id} className="group border-b border-border/30 last:border-0">
              {editing === item.id ? (
                /* ── Inline edit row ── */
                <div className="flex items-center gap-2 px-4 py-2">
                  <p className="text-sm text-white truncate flex-1 min-w-0">{item.display_name}</p>
                  <input
                    type="number"
                    value={editQty}
                    onChange={e => setEditQty(e.target.value)}
                    className="input w-20 font-mono text-sm py-1 px-2"
                    autoFocus
                    min="0.5"
                    step="0.5"
                    onKeyDown={e => {
                      if (e.key === "Enter") handleSaveEdit(item.id);
                      if (e.key === "Escape") cancelEdit();
                    }}
                  />
                  <span className="text-xs text-muted">g</span>
                  <button
                    onClick={() => handleSaveEdit(item.id)}
                    disabled={saving === item.id}
                    className="p-1 rounded hover:bg-accent-green/20 text-accent-green">
                    {saving === item.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="p-1 rounded hover:bg-surface-3 text-muted hover:text-white">
                    <X size={13} />
                  </button>
                </div>
              ) : (
                /* ── Normal row ── */
                <div className="flex items-center justify-between px-4 py-2.5 hover:bg-surface-2/50">
                  <div className="flex flex-col min-w-0">
                    <p className="text-sm text-white truncate">{item.display_name}</p>
                    <p className="text-[11px] text-muted">{item.quantity_g}g</p>
                  </div>

                  <div className="flex items-center gap-3 ml-3 shrink-0">
                    <span className="text-xs font-mono text-subtle">{item.calories.toFixed(0)} kcal</span>
                    <span className="text-[11px] text-accent-green">{item.protein_g.toFixed(1)}P</span>
                    <span className="text-[11px] text-accent-blue">{item.carbs_g.toFixed(1)}C</span>
                    <span className="text-[11px] text-accent-red">{item.fat_g.toFixed(1)}F</span>
                    <button
                      onClick={() => startEdit(item)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-surface-3 text-muted hover:text-white"
                    >
                      <Pencil size={11} />
                    </button>
                    <button
                      onClick={() => handleDelete(item.id)}
                      disabled={deleting === item.id}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-500/20 text-muted hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* ── Save as Recipe prompt ── */}
          {recipePrompt && (
            <div className="flex items-center gap-2 px-4 py-2.5 border-t border-border/50 bg-surface-2/40">
              <input
                ref={recipeInputRef}
                value={recipeName}
                onChange={e => setRecipeName(e.target.value)}
                placeholder="Recipe name…"
                className="input flex-1 text-sm py-1 px-2"
                autoFocus
                onKeyDown={e => {
                  if (e.key === "Enter") handleSaveAsRecipe();
                  if (e.key === "Escape") { setRecipePrompt(false); setRecipeName(""); }
                }}
              />
              <button
                onClick={handleSaveAsRecipe}
                disabled={savingRecipe || !recipeName.trim()}
                className="btn-primary py-1 px-3 text-xs flex items-center gap-1">
                {savingRecipe ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                Save
              </button>
              <button
                onClick={() => { setRecipePrompt(false); setRecipeName(""); }}
                className="p-1 rounded hover:bg-surface-3 text-muted hover:text-white">
                <X size={13} />
              </button>
            </div>
          )}

          {/* ── Footer buttons ── */}
          <div className="flex border-t border-border/50">
            <button
              onClick={onAddToMeal}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-xs text-muted hover:text-accent-blue hover:bg-surface-2 transition-colors"
            >
              <Plus size={13} /> Add food
            </button>
            {!recipePrompt && meal.items?.some(i => i.ingredient_id) && (
              <button
                onClick={() => { setRecipePrompt(true); setTimeout(() => recipeInputRef.current?.focus(), 50); }}
                className="flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs text-muted hover:text-accent-blue hover:bg-surface-2 transition-colors border-l border-border/50"
              >
                <BookmarkPlus size={13} /> Save as recipe
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MacroChip({ value, unit, color }) {
  return (
    <span className={`text-[11px] font-mono font-medium hidden sm:block ${color}`}>
      {value.toFixed(unit === "kcal" ? 0 : 1)}<span className="text-muted ml-0.5">{unit}</span>
    </span>
  );
}
