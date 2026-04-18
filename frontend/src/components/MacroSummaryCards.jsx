/**
 * Top summary bar — 4 macro cards exactly as in the app but consultant-dark styled.
 * Energy / Protein / Net Carbs / Fat
 * Each card: consumed / target, colour-coded progress bar, % used.
 */

const MACROS = [
  { key: "energy",    label: "Energy",    unit: "kcal", color: "#f97316" },
  { key: "protein",   label: "Protein",   unit: "g",    color: "#22c55e" },
  { key: "net_carbs", label: "Net Carbs", unit: "g",    color: "#3b82f6" },
  { key: "fat",       label: "Fat",       unit: "g",    color: "#ef4444" },
];

export default function MacroSummaryCards({ summary, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-2 animate-pulse">
        {[1,2,3,4].map(i => (
          <div key={i} className="card h-[88px] bg-surface-2" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {MACROS.map(({ key, label, unit, color }) => {
        const stat = summary?.[key];
        const consumed  = stat?.consumed  ?? 0;
        const target    = stat?.target    ?? 1;
        const remaining = stat?.remaining ?? target;
        const pct       = stat?.pct       ?? 0;
        const clamped   = Math.min(100, pct);
        const over      = pct > 100;

        return (
          <div key={key} className="card flex flex-col gap-2">
            {/* Header row */}
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-subtle uppercase tracking-wider">
                {label}
              </span>
              <span className={`text-[10px] font-mono font-medium px-1.5 py-0.5 rounded ${over ? "bg-red-500/20 text-red-400" : "bg-surface-3 text-subtle"}`}>
                {pct.toFixed(0)}%
              </span>
            </div>

            {/* Consumed / Target */}
            <div className="flex items-baseline gap-1">
              <span className="text-lg font-bold font-mono" style={{ color }}>
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
                style={{
                  width: `${clamped}%`,
                  backgroundColor: over ? "#ef4444" : color,
                }}
              />
            </div>

            {/* Remaining */}
            <p className="text-[11px] text-subtle">
              {over
                ? <span className="text-red-400">+{(consumed - target).toFixed(1)} over</span>
                : <>{remaining.toFixed(key === "energy" ? 0 : 1)} {unit} remaining</>
              }
            </p>
          </div>
        );
      })}
    </div>
  );
}
