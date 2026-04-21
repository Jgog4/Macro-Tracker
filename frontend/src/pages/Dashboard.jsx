/**
 * Main dashboard page — mirrors the app's layout:
 *  1. Macro summary cards (Energy / Protein / Net Carbs / Fat)
 *  2. Chronological meal list (Meal 1, Meal 2, …)
 *  3. Action row (Add Food | Scan | Suggest)
 */
import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";
import { mealsApi } from "../api/client";
import MacroSummaryCards from "../components/MacroSummaryCards";
import MealSection from "../components/MealSection";
import AddFoodModal from "../components/AddFoodModal";
import VisionModal from "../components/VisionModal";
import SuggestModal from "../components/SuggestModal";
import CustomMealModal from "../components/CustomMealModal";
import { Plus, Camera, Sparkles, RefreshCw, ChefHat } from "lucide-react";

export default function Dashboard({ currentDate }) {
  const [summary, setSummary]       = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [showAdd, setShowAdd]         = useState(false);
  const [showVision, setShowVision]   = useState(false);
  const [showSuggest, setShowSuggest] = useState(false);
  const [showCustom, setShowCustom]   = useState(false);
  const [newMealNumber, setNewMealNumber] = useState(null);

  const dateStr = format(currentDate, "yyyy-MM-dd");

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await mealsApi.getDay(dateStr);
      setSummary(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not load data");
    } finally {
      setLoading(false);
    }
  }, [dateStr]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  // After adding food → open next meal or specified meal
  const handleAddFood = (mealNumber) => {
    setNewMealNumber(mealNumber ?? null);
    setShowAdd(true);
  };

  const handleFoodLogged = () => {
    setShowAdd(false);
    fetchSummary();
  };

  const handleVisionSaved = () => {
    setShowVision(false);
    fetchSummary();
  };

  // ── UI ─────────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <p className="text-red-400 text-sm">{error}</p>
        <button onClick={fetchSummary} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 pt-4">

      {/* ── Macro Summary Cards ─────────────────────────────────────────────── */}
      <MacroSummaryCards summary={summary} loading={loading} />

      {/* ── Meal list ──────────────────────────────────────────────────────── */}
      {loading ? (
        <SkeletonMeals />
      ) : summary?.meals?.length === 0 ? (
        <EmptyState onAdd={() => handleAddFood(null)} />
      ) : (
        summary?.meals?.map(meal => (
          <MealSection
            key={meal.id}
            meal={meal}
            onAddToMeal={() => handleAddFood(meal.meal_number)}
            onRefresh={fetchSummary}
          />
        ))
      )}

      {/* ── Floating Action Bar ─────────────────────────────────────────────── */}
      <div className="fixed bottom-6 left-0 right-0 z-30 flex justify-center px-4">
        <div className="bg-surface-2 border border-border rounded-2xl px-2 py-2 flex items-center gap-1 shadow-2xl shadow-black/60">
          <ActionButton
            icon={<Plus size={18} />}
            label="Add Food"
            onClick={() => handleAddFood(null)}
            accent="accent-blue"
          />
          <ActionButton
            icon={<Camera size={18} />}
            label="Scan Label"
            onClick={() => setShowVision(true)}
            accent="accent-purple"
          />
          <ActionButton
            icon={<ChefHat size={18} />}
            label="Build Meal"
            onClick={() => setShowCustom(true)}
            accent="accent-purple"
          />
          <ActionButton
            icon={<Sparkles size={18} />}
            label="Suggest"
            onClick={() => setShowSuggest(true)}
            accent="accent-green"
          />
        </div>
      </div>

      {/* ── Modals ─────────────────────────────────────────────────────────── */}
      {showAdd && (
        <AddFoodModal
          dateStr={dateStr}
          defaultMealNumber={newMealNumber}
          onClose={() => setShowAdd(false)}
          onLogged={handleFoodLogged}
        />
      )}
      {showVision && (
        <VisionModal
          onClose={() => setShowVision(false)}
          onSaved={handleVisionSaved}
        />
      )}
      {showCustom && (
        <CustomMealModal
          dateStr={dateStr}
          defaultMealNumber={(summary?.meals?.length ?? 0) + 1}
          onClose={() => setShowCustom(false)}
          onLogged={() => { setShowCustom(false); fetchSummary(); }}
        />
      )}
      {showSuggest && (
        <SuggestModal
          dateStr={dateStr}
          remaining={summary ? {
            protein_g: summary.protein.remaining,
            fat_g:     summary.fat.remaining,
          } : {}}
          onClose={() => setShowSuggest(false)}
        />
      )}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function ActionButton({ icon, label, onClick, accent }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center gap-1 px-5 py-2 rounded-xl transition-colors hover:bg-surface-3`}
    >
      <span className={`text-${accent}`}>{icon}</span>
      <span className="text-[10px] text-subtle font-medium">{label}</span>
    </button>
  );
}

function EmptyState({ onAdd }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-surface-2 border border-border flex items-center justify-center text-2xl">
        🥗
      </div>
      <div>
        <p className="text-white font-medium">Nothing logged yet</p>
        <p className="text-subtle text-sm mt-1">Tap Add Food to log your first meal</p>
      </div>
      <button onClick={onAdd} className="btn-primary flex items-center gap-2">
        <Plus size={14} /> Add First Meal
      </button>
    </div>
  );
}

function SkeletonMeals() {
  return (
    <div className="flex flex-col gap-3 animate-pulse">
      {[1, 2].map(i => (
        <div key={i} className="card h-24 bg-surface-2" />
      ))}
    </div>
  );
}
