/**
 * Collapsible meal section — iOS-style white card with separator-divided rows.
 */
import { useState, useRef } from "react";
import { format, parseISO } from "date-fns";
import { ChevronDown, ChevronUp, Plus, Trash2, Utensils, Pencil, Check, X, BookmarkPlus, Copy, Loader2 } from "lucide-react";
import { mealsApi, recipesApi } from "../api/client";
import CopyMealModal from "./CopyMealModal";

export default function MealSection({ meal, onAddToMeal, onRefresh }) {
  const [open, setOpen]             = useState(true);
  const [deleting, setDeleting]     = useState(null);
  const [editing, setEditing]       = useState(null);
  const [editQty, setEditQty]       = useState("");
  const [saving, setSaving]         = useState(null);
  const [savingRecipe, setSavingRecipe] = useState(false);
  const [recipePrompt, setRecipePrompt] = useState(false);
  const [recipeName, setRecipeName]     = useState("");
  const [showCopy, setShowCopy]         = useState(false);
  const recipeInputRef = useRef();

  const time = meal.logged_at
    ? format(parseISO(meal.logged_at), "h:mm a")
    : null;

  const handleDelete = async (itemId) => {
    setDeleting(itemId);
    try { await mealsApi.deleteItem(itemId); onRefresh(); }
    catch (e) { console.error(e); }
    finally { setDeleting(null); }
  };

  const startEdit = (item) => { setEditing(item.id); setEditQty(String(item.quantity_g)); };
  const cancelEdit = () => { setEditing(null); setEditQty(""); };

  const handleSaveEdit = async (itemId) => {
    const qty = parseFloat(editQty);
    if (!qty || qty <= 0) return;
    setSaving(itemId);
    try { await mealsApi.updateItem(itemId, { quantity_g: qty }); setEditing(null); onRefresh(); }
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
              {time && <span> · {time}</span>}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4 mr-2">
          <MacroChip value={meal.total_calories}  unit="kcal" color="#FF9500" />
          <MacroChip value={meal.total_protein_g} unit="P"    color="#34C759" />
          <MacroChip value={meal.total_carbs_g}   unit="C"    color="#007AFF" />
          <MacroChip value={meal.total_fat_g}     unit="F"    color="#FF3B30" />
        </div>

        {open
          ? <ChevronUp size={16} className="text-muted shrink-0" />
          : <ChevronDown size={16} className="text-muted shrink-0" />}
      </button>

      {/* ── Items ── */}
      {showCopy && (
        <CopyMealModal
          meal={meal}
          onClose={() => setShowCopy(false)}
          onCopied={(dateStr) => { setShowCopy(false); onRefresh(); }}
        />
      )}

      {open && (
        <div className="border-t border-surface-3">
          {meal.items?.map(item => (
            <div key={item.id} className="group border-b border-surface-3 last:border-0">
              {editing === item.id ? (
                <div className="flex items-center gap-2 px-4 py-2.5">
                  <p className="text-sm text-foreground truncate flex-1 min-w-0">{item.display_name}</p>
                  <input
                    type="number"
                    value={editQty}
                    onChange={e => setEditQty(e.target.value)}
                    className="input w-20 py-1 px-2"
                    autoFocus min="0.5" step="0.5"
                    onKeyDown={e => { if (e.key === "Enter") handleSaveEdit(item.id); if (e.key === "Escape") cancelEdit(); }}
                  />
                  <span className="text-xs text-muted">g</span>
                  <button onClick={() => handleSaveEdit(item.id)} disabled={saving === item.id}
                    className="p-1 rounded-lg bg-green-50 text-accent-green">
                    {saving === item.id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                  </button>
                  <button onClick={cancelEdit} className="p-1 rounded-lg hover:bg-surface-3 text-muted">
                    <X size={13} />
                  </button>
                </div>
              ) : (
                <div className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-surface-2 transition-colors">
                  <div className="flex flex-col flex-1 min-w-0">
                    <p className="text-sm text-foreground truncate">{item.display_name}</p>
                    <p className="text-[11px] text-muted">{item.quantity_g}g</p>
                  </div>
                  <div className="flex items-center gap-3 ml-3 shrink-0">
                    <span className="text-xs font-mono text-muted">{item.calories.toFixed(0)} kcal</span>
                    <span className="text-[11px] font-medium" style={{ color: "#34C759" }}>{item.protein_g.toFixed(1)}P</span>
                    <span className="text-[11px] font-medium" style={{ color: "#007AFF" }}>{item.carbs_g.toFixed(1)}C</span>
                    <span className="text-[11px] font-medium" style={{ color: "#FF3B30" }}>{item.fat_g.toFixed(1)}F</span>
                    <button onClick={() => startEdit(item)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-surface-3 text-muted">
                      <Pencil size={11} />
                    </button>
                    <button onClick={() => handleDelete(item.id)} disabled={deleting === item.id}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red">
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Recipe prompt */}
          {recipePrompt && (
            <div className="flex items-center gap-2 px-4 py-2.5 border-t border-surface-3 bg-blue-50">
              <input
                ref={recipeInputRef}
                value={recipeName}
                onChange={e => setRecipeName(e.target.value)}
                placeholder="Recipe name…"
                className="input flex-1 py-1.5 px-2"
                autoFocus
                onKeyDown={e => { if (e.key === "Enter") handleSaveAsRecipe(); if (e.key === "Escape") { setRecipePrompt(false); setRecipeName(""); } }}
              />
              <button onClick={handleSaveAsRecipe} disabled={savingRecipe || !recipeName.trim()}
                className="btn-primary py-1.5 px-3 text-xs flex items-center gap-1">
                {savingRecipe ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Save
              </button>
              <button onClick={() => { setRecipePrompt(false); setRecipeName(""); }}
                className="p-1 rounded-lg hover:bg-surface-3 text-muted"><X size={13} /></button>
            </div>
          )}

          {/* Footer */}
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

function MacroChip({ value, unit, color }) {
  return (
    <span className="text-[11px] font-semibold font-mono hidden sm:block" style={{ color }}>
      {value.toFixed(unit === "kcal" ? 0 : 1)}<span className="text-muted ml-0.5 font-normal">{unit}</span>
    </span>
  );
}
