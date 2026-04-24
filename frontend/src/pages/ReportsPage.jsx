/**
 * ReportsPage — macro & nutrient averages over a selectable date range.
 * Opened from the hamburger menu in the app header.
 * Rendered via React portal so it sits above all other content.
 */
import { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { format, subDays } from "date-fns";
import { ArrowLeft, Loader2, BarChart2 } from "lucide-react";
import { micronutrientsApi } from "../api/client";

// ── Period presets ─────────────────────────────────────────────────────────
const PRESETS = [
  { id: "1w",  label: "1 Week",  days: 7  },
  { id: "2w",  label: "2 Weeks", days: 14 },
  { id: "1m",  label: "1 Month", days: 30 },
  { id: "custom", label: "Custom", days: null },
];

const today = () => format(new Date(), "yyyy-MM-dd");
const daysAgo = (n) => format(subDays(new Date(), n - 1), "yyyy-MM-dd");

// ── Main component ─────────────────────────────────────────────────────────
export default function ReportsPage({ onClose }) {
  const [preset, setPreset]           = useState("1w");
  const [customStart, setCustomStart] = useState(daysAgo(7));
  const [customEnd,   setCustomEnd]   = useState(today());
  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  const { start, end } = useMemo(() => {
    if (preset !== "custom") {
      const p = PRESETS.find(p => p.id === preset);
      return { start: daysAgo(p.days), end: today() };
    }
    return { start: customStart, end: customEnd };
  }, [preset, customStart, customEnd]);

  useEffect(() => {
    if (preset === "custom" && (!customStart || !customEnd || customStart > customEnd)) return;
    setData(null);
    setError(null);
    setLoading(true);
    micronutrientsApi.getRange(start, end)
      .then(res => setData(res.data))
      .catch(() => setError("Could not load report data"))
      .finally(() => setLoading(false));
  }, [start, end, preset, customStart, customEnd]);

  const avg = data?.daily_avg ?? null;
  const daysLogged = data?.days_with_data ?? 0;

  // Total calendar days in the selected range
  const totalDays = useMemo(() => {
    if (!start || !end) return 0;
    const ms = new Date(end) - new Date(start);
    return Math.round(ms / 86400000) + 1;
  }, [start, end]);

  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "white" }}>

      {/* ── Header ── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-3 shrink-0" style={{ backgroundColor: "white" }}>
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 transition-colors text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-2">
          <BarChart2 size={16} className="text-accent-blue" />
          <h1 className="text-base font-bold text-foreground">Reports</h1>
        </div>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-5">

        {/* ── Period selector ── */}
        <div className="flex flex-col gap-3">
          <div className="flex bg-surface-2 rounded-xl p-1 gap-1">
            {PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => setPreset(p.id)}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors
                  ${preset === p.id
                    ? "bg-white text-foreground shadow-sm"
                    : "text-muted hover:text-foreground"}`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Custom date pickers */}
          {preset === "custom" && (
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <label className="text-[11px] text-muted mb-1 block">From</label>
                <input
                  type="date"
                  value={customStart}
                  max={customEnd}
                  onChange={e => setCustomStart(e.target.value)}
                  className="input w-full text-sm"
                />
              </div>
              <span className="text-muted mt-5">→</span>
              <div className="flex-1">
                <label className="text-[11px] text-muted mb-1 block">To</label>
                <input
                  type="date"
                  value={customEnd}
                  min={customStart}
                  max={today()}
                  onChange={e => setCustomEnd(e.target.value)}
                  className="input w-full text-sm"
                />
              </div>
            </div>
          )}

          {/* Days logged badge */}
          {data && (
            <p className="text-[11px] text-muted text-center">
              {daysLogged} of {totalDays} day{totalDays !== 1 ? "s" : ""} logged
              {daysLogged > 0 && " · showing daily averages"}
            </p>
          )}
        </div>

        {/* ── Content ── */}
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 size={22} className="animate-spin text-muted" />
          </div>
        ) : error ? (
          <p className="text-xs text-accent-red text-center py-8">{error}</p>
        ) : !data || daysLogged === 0 ? (
          <div className="flex flex-col items-center py-16 gap-3 text-center">
            <span className="text-4xl">📊</span>
            <p className="font-semibold text-foreground">No data for this period</p>
            <p className="text-muted text-sm">Log some meals to see your averages here</p>
          </div>
        ) : (
          <>
            {/* ── Macro average cards ── */}
            <Section title="Daily Averages">
              <div className="grid grid-cols-2 gap-3">
                <MacroCard label="Calories" value={avg.calories}  unit="kcal" color="#FF9500" decimals={0} />
                <MacroCard label="Protein"  value={avg.protein_g} unit="g"    color="#34C759" decimals={1} />
                <MacroCard label="Carbs"    value={avg.carbs_g}   unit="g"    color="#007AFF" decimals={1} />
                <MacroCard label="Fat"      value={avg.fat_g}     unit="g"    color="#FF3B30" decimals={1} />
              </div>
            </Section>

            {/* ── Secondary nutrients ── */}
            <Section title="Other Nutrients (daily avg)">
              <div className="card-no-pad divide-y divide-surface-3">
                <NutrientRow label="Fiber"      value={avg.fiber_g}        unit="g"  />
                <NutrientRow label="Sugar"      value={avg.sugar_g}        unit="g"  />
                <NutrientRow label="Sodium"     value={avg.sodium_mg}      unit="mg" />
                <NutrientRow label="Potassium"  value={avg.potassium_mg}   unit="mg" />
                <NutrientRow label="Sat Fat"    value={avg.sat_fat_g}      unit="g"  />
                <NutrientRow label="Cholesterol" value={avg.cholesterol_mg} unit="mg" />
                <NutrientRow label="Omega-3 ALA" value={avg.omega3_ala_g}  unit="g"  />
                <NutrientRow label="Omega-3 EPA" value={avg.omega3_epa_g}  unit="g"  />
                <NutrientRow label="Omega-3 DHA" value={avg.omega3_dha_g}  unit="g"  />
              </div>
            </Section>

            {/* ── Vitamin & mineral highlights ── */}
            <Section title="Vitamins & Minerals (daily avg)">
              <div className="card-no-pad divide-y divide-surface-3">
                <NutrientRow label="Vitamin A"   value={avg.vitamin_a_mcg}  unit="mcg" />
                <NutrientRow label="Vitamin C"   value={avg.vitamin_c_mg}   unit="mg"  />
                <NutrientRow label="Vitamin D"   value={avg.vitamin_d_mcg}  unit="mcg" />
                <NutrientRow label="Vitamin E"   value={avg.vitamin_e_mg}   unit="mg"  />
                <NutrientRow label="Calcium"     value={avg.calcium_mg}     unit="mg"  />
                <NutrientRow label="Iron"        value={avg.iron_mg}        unit="mg"  />
                <NutrientRow label="Magnesium"   value={avg.magnesium_mg}   unit="mg"  />
                <NutrientRow label="Zinc"        value={avg.zinc_mg}        unit="mg"  />
                <NutrientRow label="B12"         value={avg.cobalamin_mcg}  unit="mcg" />
                <NutrientRow label="Folate"      value={avg.folate_mcg}     unit="mcg" />
              </div>
            </Section>
          </>
        )}

        <div className="h-4" />
      </div>
    </div>,
    document.body
  );
}

// ── Section wrapper ────────────────────────────────────────────────────────
function Section({ title, children }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold text-muted uppercase tracking-wider">{title}</p>
      {children}
    </div>
  );
}

// ── Big macro card ─────────────────────────────────────────────────────────
function MacroCard({ label, value, unit, color, decimals }) {
  return (
    <div className="bg-surface-1 rounded-xl p-4 shadow-card flex flex-col gap-1">
      <span className="text-[11px] text-muted">{label}</span>
      <span className="text-2xl font-bold font-mono" style={{ color }}>
        {value != null ? value.toFixed(decimals) : "—"}
      </span>
      <span className="text-[11px] text-muted">{unit} / day</span>
    </div>
  );
}

// ── Secondary nutrient row ────────────────────────────────────────────────
function NutrientRow({ label, value, unit }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-foreground">{label}</span>
      <span className="text-sm font-mono text-muted">
        {value != null && value > 0
          ? `${value < 10 ? value.toFixed(2) : value < 100 ? value.toFixed(1) : value.toFixed(0)} ${unit}`
          : "—"}
      </span>
    </div>
  );
}
