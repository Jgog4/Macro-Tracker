/**
 * ReportsPage — macro & nutrient averages over a selectable date range.
 * Opened from the hamburger menu in the app header.
 */
import { useState, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { format, subDays, parseISO } from "date-fns";
import { ArrowLeft, Loader2, BarChart2, Maximize2, Search, X } from "lucide-react";
import {
  ResponsiveContainer, ComposedChart, Bar, Line, LineChart,
  XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, Legend,
} from "recharts";
import { micronutrientsApi, mealsApi } from "../api/client";
import { GROUPS, formatNutrientValue } from "../constants/nutrientConfig";

// ── Helpers ────────────────────────────────────────────────────────────────
const todayStr  = () => format(new Date(), "yyyy-MM-dd");
const daysAgo   = (n) => format(subDays(new Date(), n - 1), "yyyy-MM-dd");
const yesterday = () => format(subDays(new Date(), 1), "yyyy-MM-dd");

// ── Period presets ─────────────────────────────────────────────────────────
const PRESETS = [
  { id: "1w",     label: "1 Week",  days: 7  },
  { id: "2w",     label: "2 Weeks", days: 14 },
  { id: "1m",     label: "1 Month", days: 30 },
  { id: "custom", label: "Custom",  days: null },
];

const CORE_NUTRIENTS = [
  { key: "calories",       label: "Calories",       unit: "kcal", color: "#FF9500", group: "Macros" },
  { key: "protein_g",      label: "Protein",        unit: "g",    color: "#34C759", group: "Macros" },
  { key: "carbs_g",        label: "Carbs",          unit: "g",    color: "#007AFF", group: "Macros" },
  { key: "fat_g",          label: "Fat",            unit: "g",    color: "#FF3B30", group: "Macros" },
  { key: "fiber_g",        label: "Fiber",          unit: "g",    color: "#8E8E93", group: "Daily basics" },
  { key: "sugar_g",        label: "Sugar",          unit: "g",    color: "#FF2D55", group: "Daily basics" },
  { key: "sat_fat_g",      label: "Saturated Fat",  unit: "g",    color: "#FF6B6B", group: "Daily basics" },
  { key: "sodium_mg",      label: "Sodium",         unit: "mg",   color: "#5856D6", group: "Daily basics" },
  { key: "cholesterol_mg", label: "Cholesterol",    unit: "mg",   color: "#AF52DE", group: "Daily basics" },
];

const NUTRIENT_OPTIONS = [
  ...CORE_NUTRIENTS,
  ...GROUPS.flatMap(group => group.items.map(item => ({ ...item, color: group.color, group: group.label }))),
];

const QUICK_NUTRIENT_KEYS = [
  "calories", "protein_g", "carbs_g", "fat_g", "fiber_g",
  "omega3_dha_g", "vitamin_c_mg", "iron_mg",
];

const nutrientByKey = (key) => NUTRIENT_OPTIONS.find(item => item.key === key) || NUTRIENT_OPTIONS[0];

// ── Main component ─────────────────────────────────────────────────────────
export default function ReportsPage({ onClose }) {
  const [preset,       setPreset]       = useState("1w");
  const [customStart,  setCustomStart]  = useState(daysAgo(7));
  const [customEnd,    setCustomEnd]    = useState(todayStr());
  const [includeToday, setIncludeToday] = useState(true);
  const [data,         setData]         = useState(null);
  const [series,       setSeries]       = useState([]);
  const [nutrientSeries, setNutrientSeries] = useState([]);
  const [target,       setTarget]       = useState(null);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState(null);
  const [expanded,     setExpanded]     = useState(null);
  const [trendKey,     setTrendKey]     = useState("fiber_g");
  const [showNutrientFinder, setShowNutrientFinder] = useState(false);

  // Compute start / end dates from preset + toggle
  const { start, end } = useMemo(() => {
    const endDate = includeToday ? todayStr() : yesterday();
    if (preset !== "custom") {
      const p = PRESETS.find(p => p.id === preset);
      return { start: daysAgo(p.days), end: endDate };
    }
    return {
      start: customStart,
      end:   includeToday ? customEnd : (customEnd >= todayStr() ? yesterday() : customEnd),
    };
  }, [preset, customStart, customEnd, includeToday]);

  // Total calendar days in range
  const totalDays = useMemo(() => {
    if (!start || !end || start > end) return 0;
    return Math.round((new Date(end) - new Date(start)) / 86400000) + 1;
  }, [start, end]);

  // Load target once (for reference lines on charts)
  useEffect(() => {
    mealsApi.getLatestTarget().then(res => setTarget(res.data)).catch(() => setTarget(null));
  }, []);

  useEffect(() => {
    if (!start || !end || start > end) return;
    setData(null);
    setSeries([]);
    setNutrientSeries([]);
    setError(null);
    setLoading(true);
    Promise.all([
      micronutrientsApi.getRange(start, end),
      micronutrientsApi.dailySeries(start, end),
      micronutrientsApi.nutrientSeries(start, end),
    ])
      .then(([agg, ser, nutrients]) => {
        setData(agg.data);
        setSeries((ser.data || []).map(d => ({
          ...d,
          label: format(parseISO(d.date), "MMM d"),
        })));
        setNutrientSeries((nutrients.data || []).map(d => ({
          ...d,
          label: format(parseISO(d.date), "MMM d"),
        })));
      })
      .catch(() => setError("Could not load report data"))
      .finally(() => setLoading(false));
  }, [start, end]);

  const avg        = data?.daily_avg ?? null;
  const daysLogged = data?.days_with_data ?? 0;
  const selectedNutrient = nutrientByKey(trendKey);
  const trendHasData = nutrientSeries.some(row => Number(row[trendKey]) > 0);

  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "rgb(var(--surface-1))" }}>

      {/* ── Header ── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-3 shrink-0" style={{ backgroundColor: "rgb(var(--surface-1))" }}>
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
                    ? "bg-surface-1 text-foreground shadow-sm"
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
                  max={todayStr()}
                  onChange={e => setCustomEnd(e.target.value)}
                  className="input w-full text-sm"
                />
              </div>
            </div>
          )}

          {/* Include today toggle */}
          <div className="flex items-center justify-between bg-surface-1 rounded-xl px-4 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">Include today</p>
              <p className="text-[11px] text-muted">Toggle off to exclude today's partial data</p>
            </div>
            <button
              onClick={() => setIncludeToday(v => !v)}
              className={`w-11 h-6 rounded-full transition-colors relative shrink-0
                ${includeToday ? "bg-accent-blue" : "bg-surface-3"}`}
            >
              <span
                className={`absolute top-0.5 w-5 h-5 bg-surface-1 rounded-full shadow transition-transform
                  ${includeToday ? "translate-x-5" : "translate-x-0.5"}`}
              />
            </button>
          </div>

          {/* Date range + days logged badge */}
          {data && (
            <p className="text-[11px] text-muted text-center">
              {start} → {end}
              {" · "}
              {daysLogged} of {totalDays} day{totalDays !== 1 ? "s" : ""} logged
              {daysLogged > 0 && " · daily averages"}
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
            <p className="font-semibold text-foreground">No meals logged in this period</p>
            <p className="text-muted text-sm">Log meals on the Today tab to see your averages here</p>
          </div>
        ) : (
          <>
            {/* ── Macro average cards ── */}
            <Section title="Daily Averages">
              <div className="grid grid-cols-2 gap-3">
                <MacroCard label="Calories" value={avg?.calories}   unit="kcal" color="#FF9500" decimals={0} />
                <MacroCard label="Protein"  value={avg?.protein_g}  unit="g"    color="#34C759" decimals={1} />
                <MacroCard label="Carbs"    value={avg?.carbs_g}    unit="g"    color="#007AFF" decimals={1} />
                <MacroCard label="Fat"      value={avg?.fat_g}      unit="g"    color="#FF3B30" decimals={1} />
              </div>
            </Section>

            {/* ── Calories over time ── */}
            {series.length > 0 && (
              <Section title="Calories per Day" onExpand={() => setExpanded("calories")}>
                <div className="bg-surface-1 rounded-xl p-3 shadow-card cursor-pointer" onClick={() => setExpanded("calories")}>
                  <ResponsiveContainer width="100%" height={200}>
                    <ComposedChart data={series} margin={{ top: 8, right: 10, left: 4, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={18} />
                      <YAxis tick={{ fontSize: 10, fill: "#8E8E93" }} width={38}
                        tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v} />
                      <Tooltip content={<ChartTooltip unit="kcal" />} />
                      <Bar dataKey="calories" fill="#FF9500" radius={[4, 4, 0, 0]} maxBarSize={34} />
                      {target?.calories > 0 && (
                        <ReferenceLine y={target.calories} stroke="#8E8E93" strokeDasharray="4 4"
                          label={{ value: "target", position: "right", fontSize: 9, fill: "#8E8E93" }} />
                      )}
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            )}

            {/* ── Macros over time ── */}
            {series.length > 0 && (
              <Section title="Macros per Day (g)" onExpand={() => setExpanded("macros")}>
                <div className="bg-surface-1 rounded-xl p-3 shadow-card cursor-pointer" onClick={() => setExpanded("macros")}>
                  <ResponsiveContainer width="100%" height={210}>
                    <LineChart data={series} margin={{ top: 8, right: 10, left: 4, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={18} />
                      <YAxis tick={{ fontSize: 10, fill: "#8E8E93" }} width={32} />
                      <Tooltip content={<ChartTooltip unit="g" />} />
                      <Legend wrapperStyle={{ fontSize: 11 }} iconType="plainline" />
                      <Line type="monotone" dataKey="protein_g" name="Protein" stroke="#34C759" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="carbs_g"   name="Carbs"   stroke="#007AFF" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="fat_g"     name="Fat"     stroke="#FF3B30" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </Section>
            )}

            {/* ── Individual nutrient trend ── */}
            {nutrientSeries.length > 0 && (
              <Section
                title="Nutrient Trend"
                onExpand={() => setExpanded({ type: "nutrient", nutrient: selectedNutrient })}
              >
                <div className="bg-surface-1 rounded-xl p-3 shadow-card flex flex-col gap-3">
                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_NUTRIENT_KEYS.map(key => {
                      const nutrient = nutrientByKey(key);
                      const active = trendKey === key;
                      return (
                        <button
                          key={key}
                          onClick={() => setTrendKey(key)}
                          className={`px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-colors ${
                            active ? "bg-accent-blue text-white" : "bg-surface-2 text-muted hover:text-foreground"
                          }`}
                        >
                          {nutrient.label}
                        </button>
                      );
                    })}
                    <button
                      onClick={() => setShowNutrientFinder(v => !v)}
                      className="px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-surface-2 text-accent-blue hover:text-foreground"
                    >
                      + Find nutrient
                    </button>
                  </div>

                  {showNutrientFinder && (
                    <NutrientFinder
                      selectedKey={trendKey}
                      onSelect={(key) => { setTrendKey(key); setShowNutrientFinder(false); }}
                      onClose={() => setShowNutrientFinder(false)}
                    />
                  )}

                  <button
                    className="text-left"
                    onClick={() => setExpanded({ type: "nutrient", nutrient: selectedNutrient })}
                  >
                    <div className="flex items-baseline justify-between mb-1">
                      <p className="text-sm font-semibold text-foreground">
                        {selectedNutrient.label} <span className="text-muted font-normal">per day</span>
                      </p>
                      <p className="text-xs font-mono text-muted">
                        Avg {formatNutrientValue(avg?.[trendKey])} {selectedNutrient.unit}
                      </p>
                    </div>
                    {trendHasData ? (
                      <ResponsiveContainer width="100%" height={190}>
                        <LineChart data={nutrientSeries} margin={{ top: 8, right: 10, left: 4, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
                          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={18} />
                          <YAxis tick={{ fontSize: 10, fill: "#8E8E93" }} width={42}
                            tickFormatter={v => formatTrendAxis(v)} />
                          <Tooltip content={<ChartTooltip unit={selectedNutrient.unit} />} />
                          <Line type="monotone" dataKey={trendKey} name={selectedNutrient.label}
                            stroke={selectedNutrient.color} strokeWidth={2.5} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-[190px] flex items-center justify-center text-center px-6">
                        <p className="text-xs text-muted">No recorded {selectedNutrient.label.toLowerCase()} data in this period.</p>
                      </div>
                    )}
                  </button>
                </div>
              </Section>
            )}

            {/* ── Secondary nutrients ── */}
            <Section title="Other Nutrients (daily avg)">
              <div className="card-no-pad divide-y divide-surface-3">
                <NutrientRow label="Fiber"       value={avg?.fiber_g}       unit="g"  />
                <NutrientRow label="Sugar"       value={avg?.sugar_g}       unit="g"  />
                <NutrientRow label="Sodium"      value={avg?.sodium_mg}     unit="mg" />
                <NutrientRow label="Potassium"   value={avg?.potassium_mg}  unit="mg" />
                <NutrientRow label="Saturated Fat" value={avg?.sat_fat_g}   unit="g"  />
                <NutrientRow label="Cholesterol" value={avg?.cholesterol_mg} unit="mg" />
                <NutrientRow label="Omega-3 ALA" value={avg?.omega3_ala_g}  unit="g"  />
                <NutrientRow label="Omega-3 EPA" value={avg?.omega3_epa_g}  unit="g"  />
                <NutrientRow label="Omega-3 DHA" value={avg?.omega3_dha_g}  unit="g"  />
              </div>
            </Section>

            {/* ── Vitamin & mineral highlights ── */}
            <Section title="Vitamins & Minerals (daily avg)">
              <div className="card-no-pad divide-y divide-surface-3">
                <NutrientRow label="Vitamin A"  value={avg?.vitamin_a_mcg}  unit="mcg" />
                <NutrientRow label="Vitamin C"  value={avg?.vitamin_c_mg}   unit="mg"  />
                <NutrientRow label="Vitamin D"  value={avg?.vitamin_d_mcg}  unit="mcg" />
                <NutrientRow label="Vitamin E"  value={avg?.vitamin_e_mg}   unit="mg"  />
                <NutrientRow label="Calcium"    value={avg?.calcium_mg}     unit="mg"  />
                <NutrientRow label="Iron"       value={avg?.iron_mg}        unit="mg"  />
                <NutrientRow label="Magnesium"  value={avg?.magnesium_mg}   unit="mg"  />
                <NutrientRow label="Zinc"       value={avg?.zinc_mg}        unit="mg"  />
                <NutrientRow label="B12"        value={avg?.cobalamin_mcg}  unit="mcg" />
                <NutrientRow label="Folate"     value={avg?.folate_mcg}     unit="mcg" />
              </div>
            </Section>
          </>
        )}

        <div className="h-4" />
      </div>

      {expanded && (
        <ExpandedChartModal
          type={typeof expanded === "string" ? expanded : expanded.type}
          nutrient={typeof expanded === "object" ? expanded.nutrient : null}
          series={typeof expanded === "object" ? nutrientSeries : series}
          target={target}
          onClose={() => setExpanded(null)}
        />
      )}
    </div>,
    document.body
  );
}

// ── Moving average ─────────────────────────────────────────────────────────
function withMovingAvg(series, keys, window = 7) {
  return series.map((row, i) => {
    const from = Math.max(0, i - window + 1);
    const slice = series.slice(from, i + 1);
    const out = { ...row };
    keys.forEach(k => {
      const sum = slice.reduce((a, r) => a + (r[k] || 0), 0);
      out[k] = Math.round((sum / slice.length) * 10) / 10;
    });
    return out;
  });
}

// ── Expanded fullscreen chart with 7-day moving-average toggle ───────────────
function ExpandedChartModal({ type, nutrient, series, target, onClose }) {
  const [smooth, setSmooth] = useState(false);
  const keys = type === "calories"
    ? ["calories"]
    : type === "nutrient"
      ? [nutrient.key]
      : ["protein_g", "carbs_g", "fat_g"];
  const data = smooth ? withMovingAvg(series, keys, 7) : series;

  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 10000, backgroundColor: "rgb(var(--surface-1))" }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3 shrink-0">
        <h2 className="text-base font-bold text-foreground">
          {type === "calories" ? "Calories per Day" : type === "nutrient" ? `${nutrient.label} per Day (${nutrient.unit})` : "Macros per Day (g)"}
        </h2>
        <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 text-foreground">
          <X size={18} />
        </button>
      </div>

      {/* Daily / 7-day avg toggle */}
      <div className="px-4 py-3 shrink-0">
        <div className="flex bg-surface-2 rounded-xl p-1 gap-1 max-w-xs">
          <button onClick={() => setSmooth(false)}
            className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors ${!smooth ? "bg-surface-1 text-foreground shadow-sm" : "text-muted"}`}>
            Daily
          </button>
          <button onClick={() => setSmooth(true)}
            className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors ${smooth ? "bg-surface-1 text-foreground shadow-sm" : "text-muted"}`}>
            7-day average
          </button>
        </div>
      </div>

      {/* Chart fills remaining space */}
      <div className="flex-1 px-2 pb-4 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          {type === "calories" ? (
            <ComposedChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={30} />
              <YAxis tick={{ fontSize: 11, fill: "#8E8E93" }} width={40}
                tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v} />
              <Tooltip content={<ChartTooltip unit="kcal" />} />
              {smooth
                ? <Line type="monotone" dataKey="calories" name="Calories (7d avg)" stroke="#FF9500" strokeWidth={2.5} dot={false} />
                : <Bar dataKey="calories" fill="#FF9500" radius={[3, 3, 0, 0]} maxBarSize={26} />}
              {target?.calories > 0 && (
                <ReferenceLine y={target.calories} stroke="#8E8E93" strokeDasharray="4 4"
                  label={{ value: "target", position: "right", fontSize: 10, fill: "#8E8E93" }} />
              )}
            </ComposedChart>
          ) : type === "nutrient" ? (
            <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={30} />
              <YAxis tick={{ fontSize: 11, fill: "#8E8E93" }} width={46} tickFormatter={v => formatTrendAxis(v)} />
              <Tooltip content={<ChartTooltip unit={nutrient.unit} />} />
              <Line type="monotone" dataKey={nutrient.key}
                name={smooth ? `${nutrient.label} (7d avg)` : nutrient.label}
                stroke={nutrient.color} strokeWidth={2.5} dot={false} />
            </LineChart>
          ) : (
            <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(142,142,147,0.25)" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#8E8E93" }} interval="preserveStartEnd" minTickGap={30} />
              <YAxis tick={{ fontSize: 11, fill: "#8E8E93" }} width={34} />
              <Tooltip content={<ChartTooltip unit="g" />} />
              <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
              <Line type="monotone" dataKey="protein_g" name="Protein" stroke="#34C759" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="carbs_g"   name="Carbs"   stroke="#007AFF" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="fat_g"     name="Fat"     stroke="#FF3B30" strokeWidth={2.5} dot={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>,
    document.body
  );
}

// ── Nutrient finder — search + compact categories, not a giant select list ──
function NutrientFinder({ selectedKey, onSelect, onClose }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const categories = ["All", ...new Set(NUTRIENT_OPTIONS.map(item => item.group))];
  const normalized = query.trim().toLowerCase();
  const visible = normalized
    ? NUTRIENT_OPTIONS.filter(item => `${item.label} ${item.group}`.toLowerCase().includes(normalized))
    : category === "All"
      ? QUICK_NUTRIENT_KEYS.map(nutrientByKey)
      : NUTRIENT_OPTIONS.filter(item => item.group === category);

  return (
    <div className="rounded-xl bg-surface-2 p-2.5 flex flex-col gap-2" onClick={e => e.stopPropagation()}>
      <div className="flex items-center gap-2">
        <Search size={14} className="text-muted shrink-0" />
        <input
          autoFocus
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search vitamins, minerals, amino acids…"
          className="bg-transparent outline-none text-sm text-foreground min-w-0 flex-1"
        />
        <button onClick={onClose} className="text-xs text-accent-blue font-semibold">Done</button>
      </div>
      {!normalized && (
        <div className="flex gap-1.5 overflow-x-auto pb-0.5 -mx-0.5 px-0.5">
          {categories.map(item => (
            <button
              key={item}
              onClick={() => setCategory(item)}
              className={`shrink-0 px-2 py-1 rounded-md text-[10px] font-semibold ${
                category === item ? "bg-accent-blue text-white" : "bg-surface-1 text-muted"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-2 gap-1 max-h-44 overflow-y-auto">
        {visible.map(item => (
          <button
            key={item.key}
            onClick={() => onSelect(item.key)}
            className={`text-left px-2.5 py-2 rounded-lg text-xs transition-colors ${
              selectedKey === item.key ? "bg-blue-100 text-accent-blue font-semibold" : "bg-surface-1 text-foreground hover:bg-blue-50"
            }`}
          >
            <span className="block truncate">{item.label}</span>
            <span className="text-[10px] text-muted">{item.unit} · {item.group}</span>
          </button>
        ))}
        {!visible.length && <p className="col-span-2 text-xs text-muted text-center py-3">No matching nutrient</p>}
      </div>
    </div>
  );
}

function formatTrendAxis(value) {
  const absolute = Math.abs(value || 0);
  if (absolute >= 1000) return `${(value / 1000).toFixed(1)}k`;
  if (absolute >= 100) return Math.round(value).toString();
  if (absolute >= 10) return value.toFixed(0);
  if (absolute >= 1) return value.toFixed(1);
  return value.toFixed(2);
}

// ── Chart tooltip ──────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-1 rounded-lg shadow-lg border border-surface-3 px-3 py-2 text-xs">
      <p className="font-semibold text-foreground mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color || p.fill }}>
          {p.name}: <span className="font-mono font-semibold">{formatNutrientValue(p.value)} {unit}</span>
        </p>
      ))}
    </div>
  );
}

// ── Section wrapper ────────────────────────────────────────────────────────
function Section({ title, children, onExpand }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">{title}</p>
        {onExpand && (
          <button onClick={onExpand} className="flex items-center gap-1 text-[11px] font-semibold text-accent-blue hover:opacity-70">
            <Maximize2 size={12} /> Expand
          </button>
        )}
      </div>
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
  const display = value != null && value > 0
    ? `${value < 10 ? value.toFixed(2) : value < 100 ? value.toFixed(1) : value.toFixed(0)} ${unit}`
    : "—";
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-foreground">{label}</span>
      <span className={`text-sm font-mono ${display === "—" ? "text-muted/40" : "text-muted"}`}>
        {display}
      </span>
    </div>
  );
}
