/**
 * Copy Meal modal — duplicate a meal to a different date, meal number, and time.
 */
import { useState } from "react";
import { format, addDays, subDays, parseISO } from "date-fns";
import { mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { ChevronLeft, ChevronRight, Loader2, Copy } from "lucide-react";

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}

export default function CopyMealModal({ meal, onClose, onCopied }) {
  const [targetDate, setTargetDate]   = useState(new Date());   // defaults to today
  const [mealNumber, setMealNumber]   = useState(meal.meal_number);
  const [time, setTime]               = useState(nowTimeStr());
  const [copying, setCopying]         = useState(false);
  const [error, setError]             = useState("");

  const dateStr = format(targetDate, "yyyy-MM-dd");
  const isToday = dateStr === format(new Date(), "yyyy-MM-dd");

  const goBack    = () => setTargetDate(d => subDays(d, 1));
  const goForward = () => setTargetDate(d => addDays(d, 1));

  const handleCopy = async () => {
    setCopying(true);
    setError("");
    try {
      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(
        `${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`
      );
      await mealsApi.copyMeal(meal.id, {
        target_date:        dateStr,
        target_meal_number: mealNumber,
        logged_at:          loggedAt.toISOString(),
      });
      onCopied(dateStr);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to copy meal");
    } finally {
      setCopying(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Copy Meal">
      <div className="flex flex-col gap-5">

        {/* Source info */}
        <div className="bg-surface-2 rounded-xl px-4 py-3">
          <p className="text-xs text-muted font-semibold uppercase tracking-wide mb-1">Copying</p>
          <p className="text-sm font-semibold text-foreground">
            Meal {meal.meal_number} · {meal.total_calories.toFixed(0)} kcal
          </p>
          <p className="text-[11px] text-muted mt-0.5">
            {meal.items?.length ?? 0} item{(meal.items?.length ?? 0) !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Target date */}
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">
            Target Date
          </label>
          <div className="flex items-center gap-2">
            <button onClick={goBack}
              className="w-9 h-9 rounded-xl bg-surface-2 flex items-center justify-center text-muted hover:bg-surface-3 transition-colors">
              <ChevronLeft size={16} />
            </button>
            <div className="flex-1 text-center">
              <p className="text-sm font-semibold text-foreground">
                {isToday ? "Today" : format(targetDate, "EEE, MMM d")}
              </p>
              <p className="text-[11px] text-muted">{format(targetDate, "yyyy-MM-dd")}</p>
            </div>
            <button onClick={goForward}
              className="w-9 h-9 rounded-xl bg-surface-2 flex items-center justify-center text-muted hover:bg-surface-3 transition-colors">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Meal number */}
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">
            Meal Number
          </label>
          <div className="grid grid-cols-6 gap-1">
            {[1,2,3,4,5,6].map(n => (
              <button key={n} onClick={() => setMealNumber(n)}
                className={`py-2.5 rounded-xl text-sm font-bold transition-colors
                  ${n === mealNumber
                    ? "bg-accent-blue text-white shadow-sm"
                    : "bg-surface-2 text-muted hover:bg-surface-3"}`}>
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Time */}
        <div>
          <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">
            Time
          </label>
          <input
            type="time"
            value={time}
            onChange={e => setTime(e.target.value)}
            className="input font-mono w-full"
          />
        </div>

        {error && <p className="text-accent-red text-xs">{error}</p>}

        <button
          onClick={handleCopy}
          disabled={copying}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40">
          {copying
            ? <Loader2 size={14} className="animate-spin" />
            : <Copy size={14} />}
          Copy to {isToday ? "Today" : format(targetDate, "MMM d")} · Meal {mealNumber}
        </button>
      </div>
    </ModalShell>
  );
}
