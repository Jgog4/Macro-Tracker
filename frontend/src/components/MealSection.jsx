/**
 * Collapsible meal section — "Meal 1", "Meal 2", etc.
 * Shows meal total macros in header, expandable item list.
 */
import { useState } from "react";
import { format, parseISO } from "date-fns";
import { ChevronDown, ChevronUp, Plus, Trash2, Utensils } from "lucide-react";
import { mealsApi } from "../api/client";

export default function MealSection({ meal, onAddToMeal, onRefresh }) {
  const [open, setOpen]   = useState(true);
  const [deleting, setDeleting] = useState(null);

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
            <div
              key={item.id}
              className="flex items-center justify-between px-4 py-2.5 hover:bg-surface-2/50 group"
            >
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
                  onClick={() => handleDelete(item.id)}
                  disabled={deleting === item.id}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-500/20 text-muted hover:text-red-400"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))}

          {/* Add to this meal button */}
          <button
            onClick={onAddToMeal}
            className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-muted hover:text-accent-blue hover:bg-surface-2 transition-colors border-t border-border/50"
          >
            <Plus size={13} /> Add to Meal {meal.meal_number}
          </button>
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
