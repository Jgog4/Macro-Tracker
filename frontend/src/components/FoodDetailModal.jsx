/**
 * FoodDetailModal — full-screen Cronometer-style nutrient detail view.
 *
 * Props:
 *   food    — Ingredient object (all macro + micro fields)
 *   onClose — called when user taps the back / × button
 *   onLog   — optional; shows "Add to Diary" button at bottom
 */
import { useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronUp, ArrowLeft } from "lucide-react";
import { GROUPS, RDV, formatNutrientValue } from "../constants/nutrientConfig";

// ── Source labels ──────────────────────────────────────────────────────────
const SOURCE_LABEL = {
  custom:     "Scanned",
  personal:   "Personal",
  usda:       "USDA",
  restaurant: "Restaurant",
};

// ── Macro definitions for the summary bar ─────────────────────────────────
const MACROS = [
  { key: "calories",  label: "Calories", unit: "kcal", color: "#FF9500" },
  { key: "protein_g", label: "Protein",  unit: "g",    color: "#34C759" },
  { key: "carbs_g",   label: "Carbs",    unit: "g",    color: "#007AFF" },
  { key: "fat_g",     label: "Fat",      unit: "g",    color: "#FF3B30" },
];

// ── Secondary "Nutrition Facts" rows ─────────────────────────────────────
const FACTS = [
  { key: "calories",       label: "Calories",          unit: "kcal", bold: true },
  { key: "fat_g",          label: "Total Fat",          unit: "g",    bold: true },
  { key: "sat_fat_g",      label: "Saturated Fat",      unit: "g",    indent: true },
  { key: "trans_fat_g",    label: "Trans Fat",          unit: "g",    indent: true },
  { key: "cholesterol_mg", label: "Cholesterol",        unit: "mg",   bold: true },
  { key: "sodium_mg",      label: "Sodium",             unit: "mg",   bold: true },
  { key: "carbs_g",        label: "Total Carbohydrate", unit: "g",    bold: true },
  { key: "fiber_g",        label: "Dietary Fiber",      unit: "g",    indent: true },
  { key: "sugar_g",        label: "Total Sugars",       unit: "g",    indent: true },
  { key: "protein_g",      label: "Protein",            unit: "g",    bold: true },
  { key: "potassium_mg",   label: "Potassium",          unit: "mg" },
];

// ── Main component ─────────────────────────────────────────────────────────
export default function FoodDetailModal({ food, onClose, onLog }) {
  const [openGroups, setOpenGroups] = useState({
    facts: true,
    vitamins: true,
    minerals: true,
    amino_acids: false,
    fatty_acids: false,
    carb_details: false,
  });

  const toggleGroup = (key) =>
    setOpenGroups(prev => ({ ...prev, [key]: !prev[key] }));

  const serving = food.serving_size_desc
    || (food.serving_size_g ? `${food.serving_size_g} g` : "per serving");

  // Portal to document.body to escape any overflow/stacking-context traps
  // (required on iOS Safari where position:fixed gets clipped inside scroll containers)
  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "white" }}>

      {/* ── Top bar ── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-3 shrink-0" style={{ backgroundColor: "white" }}>
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 transition-colors text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex-1 min-w-0">
          {/* Food name — wraps freely across the full header */}
          <h1 className="text-base font-bold text-foreground leading-snug">{food.name}</h1>
          <p className="text-[11px] text-muted mt-0.5">
            {SOURCE_LABEL[food.source] ?? food.source}
            {food.brand ? ` · ${food.brand}` : ""}
            {` · ${serving}`}
          </p>
        </div>
      </div>

      {/* ── Scrollable body ── */}
      <div className="flex-1 overflow-y-auto">

        {/* ── Macro summary row ── */}
        <div className="grid grid-cols-4 gap-2 px-4 py-4 border-b border-surface-3">
          {MACROS.map(m => (
            <div key={m.key} className="flex flex-col items-center bg-surface-1 rounded-xl py-2.5 shadow-card">
              <span className="text-sm font-bold font-mono" style={{ color: m.color }}>
                {food[m.key] != null ? formatNutrientValue(food[m.key]) : "—"}
              </span>
              <span className="text-[10px] text-muted mt-0.5">{m.label}</span>
            </div>
          ))}
        </div>

        {/* ── Nutrition Facts ── */}
        <CollapsibleSection
          label="Nutrition Facts"
          isOpen={openGroups.facts}
          onToggle={() => toggleGroup("facts")}
        >
          <div className="flex flex-col divide-y divide-surface-3">
            {FACTS.map(row => {
              const v = food[row.key];
              if (v == null) return null;
              return (
                <div key={row.key}
                  className={`flex items-center justify-between py-2 ${row.indent ? "pl-5" : ""}`}>
                  <span className={`text-sm ${row.bold ? "font-semibold text-foreground" : "text-subtle"}`}>
                    {row.label}
                  </span>
                  <span className={`text-sm font-mono tabular-nums ${row.bold ? "font-semibold text-foreground" : "text-muted"}`}>
                    {formatNutrientValue(v)}{row.unit}
                  </span>
                </div>
              );
            })}
          </div>
        </CollapsibleSection>

        {/* ── Micronutrient groups ── */}
        {GROUPS.map(group => {
          const withData = group.items.filter(i => food[i.key] != null);
          return (
            <CollapsibleSection
              key={group.key}
              label={group.label}
              badge={`${withData.length}/${group.items.length}`}
              color={group.color}
              isOpen={!!openGroups[group.key]}
              onToggle={() => toggleGroup(group.key)}
            >
              <div className="flex flex-col gap-3">
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
            </CollapsibleSection>
          );
        })}

        {/* Bottom padding so last item isn't hidden behind the sticky button */}
        <div className="h-6" />
      </div>

      {/* ── Sticky "Add to Diary" button ── */}
      {onLog && (
        <div className="shrink-0 px-4 py-3 border-t border-surface-3" style={{ backgroundColor: "white" }}>
          <button
            onClick={onLog}
            className="w-full btn-primary py-3 text-sm font-semibold rounded-xl"
          >
            Add to Diary
          </button>
        </div>
      )}
    </div>,
    document.body
  );
}

// ── Collapsible section wrapper ────────────────────────────────────────────
function CollapsibleSection({ label, badge, color, isOpen, onToggle, children }) {
  return (
    <div className="border-b border-surface-3">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-2 transition-colors"
      >
        <div className="flex items-center gap-2">
          {color && (
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
          )}
          <span className="text-sm font-semibold text-foreground">{label}</span>
          {badge && <span className="text-[11px] text-muted">{badge}</span>}
        </div>
        {isOpen
          ? <ChevronUp size={15} className="text-muted shrink-0" />
          : <ChevronDown size={15} className="text-muted shrink-0" />}
      </button>

      {isOpen && (
        <div className="px-4 pb-4">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Individual nutrient row — Cronometer style ────────────────────────────
// Layout: NutrientName - value / target       X%
//         ████████████░░░░░░░░░░░░░░░░░░░░░░░
function NutrientRow({ label, unit, value, rdv, color }) {
  const hasData = value != null;
  const pct     = hasData && rdv ? Math.min(100, (value / rdv) * 100) : null;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        {/* Left: Name + "- value / target" */}
        <span className={`text-sm ${hasData ? "font-medium text-foreground" : "text-muted/60"}`}>
          {label}
          {hasData && (
            <span className="font-normal text-muted">
              {" "}— {formatNutrientValue(value)}{unit}
              {rdv != null && (
                <span> / {formatNutrientValue(rdv)}{unit}</span>
              )}
            </span>
          )}
        </span>
        {/* Right: percentage */}
        <span className={`text-xs font-semibold tabular-nums shrink-0 ${
          pct == null ? "text-muted/40"
          : pct >= 100 ? "text-accent-green"
          : "text-foreground"
        }`}>
          {pct != null ? `${Math.round(pct)}%` : "—"}
        </span>
      </div>
      {/* Progress bar */}
      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
        {pct != null ? (
          <div
            className="h-full rounded-full"
            style={{
              width: `${pct}%`,
              backgroundColor: pct >= 100 ? "#34C759" : color,
              opacity: 0.85,
            }}
          />
        ) : (
          <div className="h-full rounded-full bg-surface-3 opacity-40" />
        )}
      </div>
    </div>
  );
}
