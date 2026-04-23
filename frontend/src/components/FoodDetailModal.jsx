/**
 * FoodDetailModal — full Cronometer-style nutrition detail sheet.
 *
 * Props:
 *   food    — Ingredient object from the API (all macro + micro fields)
 *   onClose — called when the user dismisses
 *   onLog   — optional; if provided, a "Log" button appears
 */
import { useState } from "react";
import { X, ChevronDown, ChevronUp, FlaskConical } from "lucide-react";
import { GROUPS, RDV, formatNutrientValue } from "../constants/nutrientConfig";

// ── Source labels + colours ────────────────────────────────────────────────
const SOURCE_META = {
  custom:     { label: "Scanned",   bg: "bg-purple-50",  text: "text-purple-600" },
  personal:   { label: "Personal",  bg: "bg-green-50",   text: "text-green-700"  },
  usda:       { label: "USDA",      bg: "bg-blue-50",    text: "text-blue-600"   },
  restaurant: { label: "Restaurant",bg: "bg-orange-50",  text: "text-orange-600" },
};

// ── Main component ─────────────────────────────────────────────────────────
export default function FoodDetailModal({ food, onClose, onLog }) {
  const [openGroups, setOpenGroups] = useState({ vitamins: true, minerals: true });
  const toggleGroup = (key) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }));

  const src     = SOURCE_META[food.source] ?? SOURCE_META.custom;
  const serving = food.serving_size_desc || (food.serving_size_g ? `${food.serving_size_g} g` : "per serving");

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      style={{ backgroundColor: "rgba(0,0,0,0.35)" }}
      onClick={onClose}
    >
      {/* Sheet */}
      <div
        className="w-full max-w-lg bg-background rounded-t-2xl shadow-2xl flex flex-col"
        style={{ maxHeight: "92dvh" }}
        onClick={e => e.stopPropagation()}
      >
        {/* ── Drag handle ── */}
        <div className="flex justify-center pt-2.5 pb-1 shrink-0">
          <div className="w-9 h-1 rounded-full bg-surface-3" />
        </div>

        {/* ── Header ── */}
        <div className="px-4 pb-3 border-b border-surface-3 shrink-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              {/* Source + brand badges */}
              <div className="flex items-center gap-1.5 flex-wrap mb-1">
                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${src.bg} ${src.text}`}>
                  {src.label}
                </span>
                {food.brand && (
                  <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-surface-2 text-muted">
                    {food.brand}
                  </span>
                )}
              </div>
              {/* Food name — wraps fully */}
              <h2 className="text-base font-bold text-foreground leading-snug">{food.name}</h2>
              <p className="text-[11px] text-muted mt-0.5">Serving: {serving}</p>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full bg-surface-2 text-muted hover:bg-surface-3 transition-colors mt-0.5"
            >
              <X size={14} />
            </button>
          </div>

          {/* Log button (optional) */}
          {onLog && (
            <button
              onClick={onLog}
              className="mt-3 w-full btn-primary py-2.5 text-sm font-semibold"
            >
              Log this food
            </button>
          )}
        </div>

        {/* ── Scrollable body ── */}
        <div className="overflow-y-auto flex-1 pb-safe">

          {/* ── Main macro cards ── */}
          <div className="grid grid-cols-4 gap-2 p-4 border-b border-surface-3">
            <MacroCard value={food.calories?.toFixed(0)}    label="kcal"    color="#FF9500" />
            <MacroCard value={(food.protein_g||0).toFixed(1)} label="Protein" color="#34C759" />
            <MacroCard value={(food.carbs_g||0).toFixed(1)}  label="Carbs"   color="#007AFF" />
            <MacroCard value={(food.fat_g||0).toFixed(1)}    label="Fat"     color="#FF3B30" />
          </div>

          {/* ── Secondary tracked fields ── */}
          <div className="px-4 py-3 border-b border-surface-3">
            <p className="text-[11px] font-semibold text-muted uppercase tracking-wide mb-2">
              Nutrition Facts
            </p>
            <div className="flex flex-col gap-1.5">
              <FactRow label="Calories"         value={food.calories}        unit="kcal" bold />
              <FactRow label="Total Fat"         value={food.fat_g}           unit="g"    bold />
              <FactRow label="  Saturated Fat"   value={food.sat_fat_g}       unit="g"    indent />
              <FactRow label="  Trans Fat"        value={food.trans_fat_g}     unit="g"    indent />
              <FactRow label="Cholesterol"       value={food.cholesterol_mg}  unit="mg"   bold />
              <FactRow label="Sodium"            value={food.sodium_mg}       unit="mg"   bold />
              <FactRow label="Total Carbohydrate"value={food.carbs_g}         unit="g"    bold />
              <FactRow label="  Dietary Fiber"   value={food.fiber_g}         unit="g"    indent />
              <FactRow label="  Total Sugars"    value={food.sugar_g}         unit="g"    indent />
              <FactRow label="Protein"           value={food.protein_g}       unit="g"    bold />
              {food.potassium_mg  != null && <FactRow label="Potassium"  value={food.potassium_mg}  unit="mg" />}
            </div>
          </div>

          {/* ── Micronutrient groups ── */}
          <div className="px-4 pt-3 pb-1 flex items-center gap-2 border-b border-surface-3">
            <div className="w-6 h-6 rounded-md bg-purple-50 flex items-center justify-center">
              <FlaskConical size={12} className="text-accent-purple" />
            </div>
            <p className="text-[11px] font-semibold text-muted uppercase tracking-wide">Micronutrients</p>
          </div>

          {GROUPS.map(group => (
            <MicroGroup
              key={group.key}
              group={group}
              food={food}
              isOpen={!!openGroups[group.key]}
              onToggle={() => toggleGroup(group.key)}
            />
          ))}

          {/* Bottom spacer */}
          <div className="h-6" />
        </div>
      </div>
    </div>
  );
}

// ── Macro summary card ─────────────────────────────────────────────────────
function MacroCard({ value, label, color }) {
  return (
    <div className="flex flex-col items-center bg-surface-1 rounded-xl py-2.5 shadow-card">
      <span className="text-sm font-bold font-mono" style={{ color }}>{value ?? "—"}</span>
      <span className="text-[10px] text-muted mt-0.5">{label}</span>
    </div>
  );
}

// ── Nutrition-label style row ──────────────────────────────────────────────
function FactRow({ label, value, unit, bold, indent }) {
  if (value == null) return null;
  return (
    <div className={`flex items-center justify-between ${indent ? "pl-4" : ""}`}>
      <span className={`text-xs ${bold ? "font-semibold text-foreground" : "text-subtle"}`}>
        {label.replace(/^\s+/, "")}
      </span>
      <span className={`text-xs font-mono ${bold ? "font-semibold text-foreground" : "text-muted"}`}>
        {formatNutrientValue(value)}{unit}
      </span>
    </div>
  );
}

// ── Micronutrient group (collapsible) ─────────────────────────────────────
function MicroGroup({ group, food, isOpen, onToggle }) {
  const withData = group.items.filter(i => food[i.key] != null).length;

  return (
    <div className="border-b border-surface-3 last:border-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: group.color }}
          />
          <span className="text-sm font-semibold text-foreground">{group.label}</span>
          <span className="text-[11px] text-muted">{withData}/{group.items.length}</span>
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
              value={food[item.key] ?? null}
              rdv={RDV[item.key] ?? null}
              color={group.color}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Individual nutrient row with progress bar ─────────────────────────────
function NutrientRow({ label, unit, value, rdv, color }) {
  const hasData = value != null;
  const pct     = hasData && rdv ? Math.min(100, (value / rdv) * 100) : 0;

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-foreground">{label}</span>
        <span className={`text-xs font-mono ${hasData ? "text-foreground" : "text-muted/50"}`}>
          {hasData ? `${formatNutrientValue(value)} ${unit}` : "—"}
          {hasData && rdv && (
            <span className="text-muted ml-1 font-normal">
              / {formatNutrientValue(rdv)}
            </span>
          )}
        </span>
      </div>
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
        <div className="h-1 bg-surface-3 rounded-full opacity-30" />
      )}
    </div>
  );
}
