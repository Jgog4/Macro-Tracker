/**
 * Daily macro summary — Cronometer-style horizontal progress bars.
 * Energy / Protein / Net Carbs / Fat, each a full-width row with a bar.
 */
const MACROS = [
  { key: "energy",    label: "Energy",    unit: "kcal", color: "#FF9500", decimals: 0 },
  { key: "protein",   label: "Protein",   unit: "g",    color: "#34C759", decimals: 1 },
  { key: "net_carbs", label: "Net Carbs", unit: "g",    color: "#30B0C7", decimals: 1 },
  { key: "fat",       label: "Fat",       unit: "g",    color: "#AF52DE", decimals: 1 },
];

export default function MacroSummaryCards({ summary, loading, onEditTargets }) {
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

      {MACROS.map(({ key, label, unit, color, decimals }) => {
        const stat      = summary?.[key];
        const consumed  = stat?.consumed  ?? 0;
        const target    = stat?.target    ?? 1;
        const pct       = target > 0 ? (consumed / target) * 100 : 0;
        const clamped   = Math.min(100, pct);
        const over      = pct > 100.5;

        return (
          <div key={key} className="flex flex-col gap-1.5">
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
          </div>
        );
      })}
    </div>
  );
}
