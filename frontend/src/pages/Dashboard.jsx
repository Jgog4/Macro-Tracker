/**
 * Main dashboard — daily diary with macro summary + meal list.
 */
import { useState, useEffect, useCallback } from "react";
import { format } from "date-fns";
import { mealsApi } from "../api/client";
import MacroSummaryCards from "../components/MacroSummaryCards";
import MealSection from "../components/MealSection";
import AddFoodModal from "../components/AddFoodModal";
import SuggestModal from "../components/SuggestModal";
import CustomMealModal from "../components/CustomMealModal";
import { Plus, Sparkles, RefreshCw, ChefHat, Loader2 } from "lucide-react";

export default function Dashboard({ currentDate, onOpenAdd, onOpenVision }) {
  const [summary, setSummary]         = useState(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [showAdd, setShowAdd]         = useState(false);
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

  useEffect(() => { fetchSummary(); }, [fetchSummary]);

  const handleAddFood = (mealNumber) => {
    setNewMealNumber(mealNumber ?? null);
    setShowAdd(true);
  };

  const handleFoodLogged = () => {
    setShowAdd(false);
    fetchSummary();
  };

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
        <p className="text-accent-red text-sm">{error}</p>
        <button onClick={fetchSummary} className="btn-primary flex items-center gap-2">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 pt-4">

      {/* ── Macro Summary ── */}
      <MacroSummaryCards summary={summary} loading={loading} />

      {/* ── Quick actions ── */}
      <div className="flex gap-2">
        <button
          onClick={() => setShowCustom(true)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-surface-1 rounded-xl shadow-card text-sm font-medium text-accent-blue">
          <ChefHat size={15} /> Build Meal
        </button>
        <button
          onClick={() => setShowSuggest(true)}
          className="flex-1 flex items-center justify-center gap-1.5 py-2.5 bg-surface-1 rounded-xl shadow-card text-sm font-medium text-accent-purple">
          <Sparkles size={15} /> Suggest
        </button>
      </div>

      {/* ── Meal list ── */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 size={22} className="animate-spin text-muted" />
        </div>
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

      {/* ── Modals ── */}
      {showAdd && (
        <AddFoodModal
          dateStr={dateStr}
          defaultMealNumber={newMealNumber}
          onClose={() => setShowAdd(false)}
          onLogged={handleFoodLogged}
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

function EmptyState({ onAdd }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-surface-1 shadow-card flex items-center justify-center text-3xl">
        🥗
      </div>
      <div>
        <p className="font-semibold text-foreground">Nothing logged yet</p>
        <p className="text-muted text-sm mt-1">Tap + to log your first meal</p>
      </div>
      <button onClick={onAdd} className="btn-primary flex items-center gap-2">
        <Plus size={14} /> Add First Meal
      </button>
    </div>
  );
}
