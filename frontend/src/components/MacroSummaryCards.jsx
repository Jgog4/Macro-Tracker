/**
 * Top summary — 4 macro cards: Energy / Protein / Net Carbs / Fat
 */
const MACROS = [
  { key: "energy",    label: "Energy",    unit: "kcal", color: "#FF9500" },
  { key: "protein",   label: "Protein",   unit: "g",    color: "#34C759" },
  { key: "net_carbs", label: "Net Carbs", unit: "g",    color: "#007AFF" },
  { key: "fat",       label: "Fat",       unit: "g",    color: "#FF3B30" },
];

export default function MacroSummaryCards({ summary, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2 animate-pulse">
        {[1,2,3,4].map(i => (
          <div key={i} className="bg-surface-1 rounded-xl h-24 shadow-card" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {MACROS.map(({ key, label, unit, color }) => {
        const stat      = summary?.[key];
        const consumed  = stat?.consumed  ?? 0;
        const target    = stat?.target    ?? 1;
        const remaining = stat?.remaining ?? target;
        const pct       = stat?.pct       ?? 0;
        const clamped   = Math.min(100, pct);
        const over      = pct > 100;

        return (
          <div key={key} className="card flex flex-col gap-2">
            {/* Header */}
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold text-muted uppercase tracking-wide">
                {label}
              </span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md
                ${over ? "bg-red-100 text-accent-red" : "bg-surface-3 text-muted"}`}>
                {pct.toFixed(0)}%
              </span>
            </div>

            {/* Consumed / Target */}
            <div className="flex items-baseline gap-1">
              <span className="text-xl font-bold font-mono" style={{ color }}>
                {consumed.toFixed(key === "energy" ? 0 : 1)}
              </span>
              <span className="text-xs text-muted">
                / {target.toFixed(key === "energy" ? 0 : 1)} {unit}
              </span>
            </div>

            {/* Progress bar */}
            <div className="macro-bar">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${clamped}%`, backgroundColor: over ? "#FF3B30" : color }}
              />
            </div>

            {/* Remaining */}
            <p className="text-[11px] text-muted">
              {over
                ? <span className="text-accent-red font-medium">+{(consumed - target).toFixed(1)} over</span>
                : <>{remaining.toFixed(key === "energy" ? 0 : 1)} {unit} left</>
              }
            </p>
          </div>
        );
      })}
    </div>
  );
}
