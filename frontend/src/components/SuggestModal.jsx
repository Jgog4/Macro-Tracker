/**
 * "What should I eat?" suggestion modal.
 * Queries /suggest/ with today's remaining macros.
 * Shows top 3 restaurant/custom items with fit score.
 */
import { useState, useEffect } from "react";
import { suggestApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { Loader2, Sparkles, TrendingDown } from "lucide-react";

export default function SuggestModal({ dateStr, remaining, onClose }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState("");

  useEffect(() => {
    suggestApi.suggest({ log_date: dateStr, top_n: 3 })
      .then(r => setSuggestions(r.data))
      .catch(e => setError(e.response?.data?.detail || "Could not load suggestions"))
      .finally(() => setLoading(false));
  }, [dateStr]);

  return (
    <ModalShell onClose={onClose} title="What Should I Eat?">
      {/* Remaining budget */}
      <div className="card-sm flex gap-6">
        <BudgetStat label="Protein remaining" value={remaining.protein_g} unit="g" color="text-accent-green" />
        <BudgetStat label="Fat remaining"     value={remaining.fat_g}     unit="g" color="text-accent-red" />
      </div>

      <p className="text-xs text-muted">
        Best matches from your restaurant database based on remaining fat &amp; protein budget.
      </p>

      {loading ? (
        <div className="flex justify-center py-10">
          <Loader2 size={20} className="animate-spin text-muted" />
        </div>
      ) : error ? (
        <p className="text-red-400 text-sm">{error}</p>
      ) : suggestions.length === 0 ? (
        <p className="text-muted text-sm text-center py-8">No suggestions — macros may already be met!</p>
      ) : (
        <div className="flex flex-col gap-2">
          {suggestions.map((s, i) => (
            <SuggestionCard key={s.ingredient.id} suggestion={s} rank={i + 1} />
          ))}
        </div>
      )}
    </ModalShell>
  );
}

function SuggestionCard({ suggestion, rank }) {
  const { ingredient: ing, fit_score, delta_protein_g, delta_fat_g } = suggestion;
  const scoreColor = fit_score > 0.7 ? "text-accent-green" : fit_score > 0.4 ? "text-accent-orange" : "text-muted";

  return (
    <div className="card-sm flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-muted">#{rank}</span>
            <p className="text-sm font-semibold">{ing.name}</p>
          </div>
          {ing.brand && <p className="text-[11px] text-muted mt-0.5">{ing.brand} · {ing.serving_size_desc}</p>}
        </div>
        <div className="flex flex-col items-end">
          <span className={`text-xs font-bold font-mono ${scoreColor}`}>{(fit_score * 100).toFixed(0)}% fit</span>
          <Sparkles size={12} className={scoreColor} />
        </div>
      </div>

      <div className="flex gap-4">
        <Macro label="Cal"  value={ing.calories}  unit="kcal" color="text-accent-orange" />
        <Macro label="P"    value={ing.protein_g} unit="g"    color="text-accent-green" />
        <Macro label="F"    value={ing.fat_g}     unit="g"    color="text-accent-red" />
        <Macro label="C"    value={ing.carbs_g}   unit="g"    color="text-accent-blue" />
      </div>

      {/* Delta indicators */}
      <div className="flex gap-4 text-[10px] text-muted">
        <span>
          <TrendingDown size={10} className="inline mr-0.5" />
          Protein delta: <span className={delta_protein_g >= 0 ? "text-accent-green" : "text-accent-red"}>{delta_protein_g > 0 ? "+" : ""}{delta_protein_g.toFixed(1)}g</span>
        </span>
        <span>
          Fat delta: <span className={delta_fat_g >= 0 ? "text-accent-green" : "text-accent-red"}>{delta_fat_g > 0 ? "+" : ""}{delta_fat_g.toFixed(1)}g</span>
        </span>
      </div>
    </div>
  );
}

function BudgetStat({ label, value, unit, color }) {
  return (
    <div>
      <p className="text-[10px] text-muted">{label}</p>
      <p className={`text-lg font-bold font-mono ${color}`}>
        {(value || 0).toFixed(1)}<span className="text-xs text-muted ml-0.5">{unit}</span>
      </p>
    </div>
  );
}

function Macro({ label, value, unit, color }) {
  return (
    <div>
      <span className={`text-sm font-bold font-mono ${color}`}>{(value || 0).toFixed(1)}</span>
      <span className="text-[10px] text-muted ml-0.5">{label}</span>
    </div>
  );
}
