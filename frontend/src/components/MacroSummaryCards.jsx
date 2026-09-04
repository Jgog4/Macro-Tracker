/**
 * Daily macro summary — Cronometer-style horizontal progress bars.
 * Energy / Protein / Net Carbs / Fat, each a full-width row with a bar.
 */
import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Loader2 } from "lucide-react";
import { micronutrientsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const MACROS = [
  { key: "energy",    nutrient: "calories", label: "Energy",    unit: "kcal", color: "#FF9500", decimals: 0 },
  { key: "protein",   nutrient: "protein_g", label: "Protein",   unit: "g",    color: "#34C759", decimals: 1 },
  { key: "net_carbs", nutrient: "carbs_g", label: "Net Carbs", unit: "g",    color: "#30B0C7", decimals: 1 },
  { key: "fat",       nutrient: "fat_g", label: "Fat",       unit: "g",    color: "#AF52DE", decimals: 1 },
];

export default function MacroSummaryCards({ summary, loading, currentDate, onEditTargets }) {
  const [selectedMacro, setSelectedMacro] = useState(null);
  if (loading) {
    return (
      <div className="card flex flex-col gap-4 animate-pulse">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="flex flex-col gap-2">
            <div className="h-3 bg-surface-2 rounded w-2/3" />
            <div className="h-2 bg-surface-2 rounded-full w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="card flex flex-col gap-3.5">
      {/* Header row */}
      <div className="flex items-center justify-between -mb-0.5">
        <span className="text-[11px] font-semibold text-muted uppercase tracking-wide">Consumed / Target</span>
        {onEditTargets && (
          <button
            onClick={onEditTargets}
            className="text-[11px] font-semibold text-accent-blue hover:opacity-70 transition-opacity"
          >
            Edit targets
          </button>
        )}
      </div>

      {MACROS.map((macro) => {
        const { key, label, unit, color, decimals } = macro;
        const stat      = summary?.[key];
        const consumed  = stat?.consumed  ?? 0;
        const target    = stat?.target    ?? 1;
        const pct       = target > 0 ? (consumed / target) * 100 : 0;
        const clamped   = Math.min(100, pct);
        const over      = pct > 100.5;

        return (
          <button
            key={key}
            onClick={() => setSelectedMacro(macro)}
            className="flex flex-col gap-1.5 text-left rounded-lg -mx-1 px-1 py-0.5 hover:bg-surface-2 transition-colors"
            aria-label={`View ${label} sources`}
          >
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-foreground">
                <span className="font-semibold">{label}</span>
                <span className="text-muted"> · {consumed.toFixed(decimals)} / {target.toFixed(decimals)} {unit}</span>
              </span>
              <span className={`text-sm font-semibold font-mono ${over ? "text-accent-green" : "text-muted"}`}>
                {Math.round(pct)}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-surface-2 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${clamped}%`, backgroundColor: color }}
              />
            </div>
          </button>
        );
      })}

      {selectedMacro && currentDate && (
        <MacroSourcesModal
          macro={selectedMacro}
          currentDate={currentDate}
          onClose={() => setSelectedMacro(null)}
        />
      )}
    </div>
  );
}

function MacroSourcesModal({ macro, currentDate, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const dateStr = format(currentDate, "yyyy-MM-dd");

  useEffect(() => {
    let active = true;
    micronutrientsApi.getSources(macro.nutrient, dateStr, dateStr)
      .then(res => { if (active) setData(res.data); })
      .catch(() => { if (active) setError("Could not load food sources"); });
    return () => { active = false; };
  }, [macro.nutrient, dateStr]);

  const total = data?.total ?? 0;
  return (
    <ModalShell onClose={onClose} title={`${macro.label} sources`}>
      <p className="text-xs text-muted -mt-1 mb-3">{format(currentDate, "MMMM d, yyyy")}</p>
      {!data && !error ? (
        <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-muted" /></div>
      ) : error ? (
        <p className="text-sm text-accent-red text-center py-8">{error}</p>
      ) : (
        <>
          <div className="rounded-xl bg-surface-2 px-4 py-3 flex items-end justify-between">
            <span className="text-xs text-muted">Total</span>
            <span className="font-mono text-lg font-bold text-foreground">
              {total.toFixed(macro.decimals)} {macro.unit}
            </span>
          </div>
          {data.sources.length ? (
            <div className="divide-y divide-surface-3">
              {data.sources.map((source, index) => {
                const pct = total ? Math.min(100, (source.value / total) * 100) : 0;
                return (
                  <div key={`${source.name}-${index}`} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{source.name}</p>
                        <p className="text-[11px] text-muted">{source.quantity_g.toFixed(1)} g</p>
                      </div>
                      <span className="font-mono text-sm text-foreground shrink-0">
                        {source.value.toFixed(macro.decimals)} {macro.unit}
                      </span>
                    </div>
                    <div className="h-1 mt-2 bg-surface-3 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: macro.color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted text-center py-8">No logged foods supplied this nutrient today.</p>
          )}
        </>
      )}
    </ModalShell>
  );
}
