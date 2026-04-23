/**
 * MicronutrientPanel — collapsible section below meal list in Today tab.
 *
 * Shows totals (or daily averages for week/month) vs. reference daily values,
 * grouped into: Vitamins · Minerals · Amino Acids · Fatty Acids · Carb Details.
 *
 * N/A is shown when the period has zero data for a nutrient.
 * RDV reference values are standard adult male FDA Daily Values.
 */
import { useState, useEffect, useCallback } from "react";
import { format, startOfWeek, endOfWeek, startOfMonth, endOfMonth } from "date-fns";
import { ChevronDown, ChevronUp, FlaskConical, Loader2 } from "lucide-react";
import { micronutrientsApi } from "../api/client";
import { RDV, GROUPS, formatNutrientValue } from "../constants/nutrientConfig";

// ── Period helpers ─────────────────────────────────────────────────────────
function getPeriodRange(currentDate, period) {
  const d = new Date(currentDate);
  if (period === "day") {
    const s = format(d, "yyyy-MM-dd");
    return { start: s, end: s };
  }
  if (period === "week") {
    return {
      start: format(startOfWeek(d, { weekStartsOn: 1 }), "yyyy-MM-dd"),
      end:   format(endOfWeek(d,   { weekStartsOn: 1 }), "yyyy-MM-dd"),
    };
  }
  // month
  return {
    start: format(startOfMonth(d), "yyyy-MM-dd"),
    end:   format(endOfMonth(d),   "yyyy-MM-dd"),
  };
}

// ── Main component ─────────────────────────────────────────────────────────
export default function MicronutrientPanel({ currentDate }) {
  const [open, setOpen]     = useState(false);
  const [period, setPeriod] = useState("day");
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState(null);
  const [openGroups, setOpenGroups] = useState({ vitamins: true });

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { start, end } = getPeriodRange(currentDate, period);
      const res = await micronutrientsApi.getRange(start, end);
      setData(res.data);
    } catch (e) {
      setError("Could not load micronutrient data");
    } finally {
      setLoading(false);
    }
  }, [currentDate, period]);

  useEffect(() => {
    if (open) fetchData();
  }, [open, fetchData]);

  const toggleGroup = (key) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }));

  // Show per-day averages for week/month, absolute for day
  const values = data
    ? (period === "day" ? data.totals : data.daily_avg)
    : null;

  return (
    <div className="card-no-pad">
      {/* ── Panel header ── */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2 transition-colors">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-purple-50 flex items-center justify-center shrink-0">
            <FlaskConical size={14} className="text-accent-purple" />
          </div>
          <div className="text-left">
            <p className="text-sm font-semibold text-foreground">Micronutrients</p>
            <p className="text-[11px] text-muted">Vitamins · Minerals · Amino Acids · more</p>
          </div>
        </div>
        {open
          ? <ChevronUp size={16} className="text-muted shrink-0" />
          : <ChevronDown size={16} className="text-muted shrink-0" />}
      </button>

      {open && (
        <div className="border-t border-surface-3">
          {/* ── Period toggle ── */}
          <div className="px-4 py-3 border-b border-surface-3">
            <div className="flex bg-surface-2 rounded-xl p-1 gap-1">
              {["day", "week", "month"].map(p => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors capitalize
                    ${period === p
                      ? "bg-white text-foreground shadow-sm"
                      : "text-muted hover:text-foreground"}`}>
                  {p === "day" ? "Today" : p === "week" ? "This Week" : "This Month"}
                </button>
              ))}
            </div>
            {data && period !== "day" && (
              <p className="text-[11px] text-muted mt-2 text-center">
                Showing daily averages · {data.days_with_data} day{data.days_with_data !== 1 ? "s" : ""} logged
              </p>
            )}
          </div>

          {/* ── Content ── */}
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 size={20} className="animate-spin text-muted" />
            </div>
          ) : error ? (
            <p className="text-xs text-accent-red px-4 py-4 text-center">{error}</p>
          ) : data ? (
            <div>
              {GROUPS.map(group => (
                <NutrientGroup
                  key={group.key}
                  group={group}
                  values={values}
                  isOpen={!!openGroups[group.key]}
                  onToggle={() => toggleGroup(group.key)}
                />
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

// ── Nutrient group collapsible ─────────────────────────────────────────────
function NutrientGroup({ group, values, isOpen, onToggle }) {
  // Count how many items in this group have actual data
  const withData = group.items.filter(i => values?.[i.key] != null).length;

  return (
    <div className="border-b border-surface-3 last:border-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-2 transition-colors">
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: group.color }}
          />
          <span className="text-sm font-semibold text-foreground">{group.label}</span>
          <span className="text-[11px] text-muted">
            {withData}/{group.items.length} tracked
          </span>
        </div>
        {isOpen
          ? <ChevronUp size={14} className="text-muted shrink-0" />
          : <ChevronDown size={14} className="text-muted shrink-0" />}
      </button>

      {isOpen && (
        <div className="px-4 pb-3 flex flex-col gap-2">
          {group.items.map(item => (
            <NutrientRow
              key={item.key}
              label={item.label}
              unit={item.unit}
              value={values?.[item.key] ?? null}
              rdv={RDV[item.key] ?? null}
              color={group.color}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Individual nutrient row ───────────────────────────────────────────────
function NutrientRow({ label, unit, value, rdv, color }) {
  const hasData = value != null;
  const pct     = hasData && rdv ? Math.min(100, (value / rdv) * 100) : 0;

  const formatVal = formatNutrientValue;

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-foreground">{label}</span>
        <span className={`text-xs font-mono ${hasData ? "text-foreground" : "text-muted/50"}`}>
          {hasData ? `${formatVal(value)} ${unit}` : "—"}
          {hasData && rdv && (
            <span className="text-muted ml-1 font-normal">
              / {formatVal(rdv)}
            </span>
          )}
        </span>
      </div>
      {/* Progress bar — only shown when we have both a value and an RDV */}
      {hasData && rdv ? (
        <div className="h-1 bg-surface-3 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${pct}%`,
              backgroundColor: pct >= 100 ? "#34C759" : color,
              opacity: 0.8,
            }}
          />
        </div>
      ) : (
        // Thin placeholder line when no data
        <div className="h-1 bg-surface-3 rounded-full opacity-40" />
      )}
    </div>
  );
}
