/**
 * Log an ingredient or restaurant item to a meal from the Library.
 * Shows date navigator, meal selector, quantity, time, and live macros.
 */
import { useState, useEffect, useCallback } from "react";
import { format, addDays, subDays } from "date-fns";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function LogFoodModal({ food, onClose, onLogged }) {
  const [targetDate, setTargetDate] = useState(new Date());
  const [mealNumber, setMealNumber] = useState(1);
  const [qty,        setQty]        = useState(String(food.serving_size_g || 100));
  const [time,       setTime]       = useState(nowTimeStr());
  const [logging,    setLogging]    = useState(false);
  const [error,      setError]      = useState("");

  const dateStr = format(targetDate, "yyyy-MM-dd");
  const isToday = dateStr === format(new Date(), "yyyy-MM-dd");

  const [mealTimes,  setMealTimes]  = useState({});
  const [timeEdited, setTimeEdited] = useState(false);

  // Fetch meal times for the selected date
  const fetchMealTimes = useCallback((dStr) => {
    mealsApi.getDay(dStr).then(res => {
      const map = {};
      (res.data?.meals || []).forEach(meal => {
        if (meal.logged_at) {
          const d = new Date(meal.logged_at);
          map[meal.meal_number] = `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
        }
      });
      setMealTimes(map);
    }).catch(() => {});
  }, []);

  // Fetch on open, and re-fetch when date changes
  useEffect(() => { fetchMealTimes(dateStr); }, [dateStr, fetchMealTimes]);

  // Auto-fill time whenever meal or fetched times change (unless user edited manually)
  useEffect(() => {
    if (timeEdited) return;
    setTime(mealTimes[mealNumber] || nowTimeStr());
  }, [mealNumber, mealTimes]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMealChange = useCallback((n) => {
    setTimeEdited(false);
    setMealNumber(n);
  }, []);

  const qtyNum  = parseFloat(qty) || 0;
  const baseG   = food.serving_size_g || (qtyNum || 100);
  const ratio   = qtyNum / baseG;
  const live    = {
    calories: (food.calories  || 0) * ratio,
    protein:  (food.protein_g || 0) * ratio,
    carbs:    (food.carbs_g   || 0) * ratio,
    fat:      (food.fat_g     || 0) * ratio,
  };

  const handleLog = async () => {
    if (!qty || qtyNum <= 0) return;
    setLogging(true);
    setError("");
    try {
      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(
        `${dateStr}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`
      );
      await mealsApi.logFood({
        log_date:    dateStr,
        meal_number: mealNumber,
        logged_at:   loggedAt.toISOString(),
        items: [{ ingredient_id: food.id, quantity_g: qtyNum }],
      });
      onLogged?.();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to log food");
    } finally {
      setLogging(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Log Food">
      <div className="flex flex-col gap-4">

        {/* Food info */}
        <div className="bg-surface-2 rounded-xl px-4 py-3">
          <p className="text-sm font-semibold text-foreground">{food.name}</p>
          {food.brand && <p className="text-xs text-muted mt-0.5">{food.brand}</p>}
        </div>

        {/* Date */}
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">Date</label>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTargetDate(d => subDays(d, 1))}
              className="w-9 h-9 rounded-xl bg-surface-2 flex items-center justify-center text-muted hover:bg-surface-3 transition-colors"
            >
              <ChevronLeft size={16} />
            </button>
            <div className="flex-1 text-center">
              <p className="text-sm font-semibold text-foreground">
                {isToday ? "Today" : format(targetDate, "EEE, MMM d")}
              </p>
              <p className="text-[11px] text-muted">{dateStr}</p>
            </div>
            <button
              onClick={() => setTargetDate(d => addDays(d, 1))}
              className="w-9 h-9 rounded-xl bg-surface-2 flex items-center justify-center text-muted hover:bg-surface-3 transition-colors"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Meal selector */}
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">Meal</label>
          <div className="grid grid-cols-6 gap-1">
            {[1, 2, 3, 4, 5, 6].map(n => (
              <button
                key={n}
                onClick={() => handleMealChange(n)}
                className={`py-2.5 rounded-xl text-sm font-bold transition-colors
                  ${n === mealNumber
                    ? "bg-accent-blue text-white shadow-sm"
                    : "bg-surface-2 text-muted hover:bg-surface-3"}`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Quantity + Time */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Quantity (g)</label>
            <input
              type="number"
              value={qty}
              onChange={e => setQty(e.target.value)}
              className="input font-mono"
              placeholder="100"
              min="1"
              step="0.5"
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Time</label>
            <input
              type="time"
              value={time}
              onChange={e => { setTime(e.target.value); setTimeEdited(true); }}
              className="input font-mono"
            />
          </div>
        </div>

        {/* Live macros */}
        <div className="bg-surface-2 rounded-2xl p-4">
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Calories", value: live.calories, unit: "kcal", color: "#FF9500" },
              { label: "Protein",  value: live.protein,  unit: "g",    color: "#34C759" },
              { label: "Carbs",    value: live.carbs,    unit: "g",    color: "#007AFF" },
              { label: "Fat",      value: live.fat,      unit: "g",    color: "#FF3B30" },
            ].map(({ label, value, unit, color }) => (
              <div key={label} className="flex flex-col items-center">
                <span className="text-base font-bold font-mono" style={{ color }}>
                  {value >= 10 ? Math.round(value) : value.toFixed(1)}
                </span>
                <span className="text-[10px] text-muted mt-0.5">{unit}</span>
                <span className="text-[9px] text-subtle">{label}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-muted mt-2 text-center">
            For {qtyNum > 0 ? `${qtyNum}g` : "—"} serving
          </p>
        </div>

        {error && <p className="text-accent-red text-xs">{error}</p>}

        <button
          onClick={handleLog}
          disabled={logging || qtyNum <= 0}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
        >
          {logging && <Loader2 size={14} className="animate-spin" />}
          Log to {isToday ? "Today" : format(targetDate, "MMM d")} · Meal {mealNumber}
        </button>
      </div>
    </ModalShell>
  );
}
