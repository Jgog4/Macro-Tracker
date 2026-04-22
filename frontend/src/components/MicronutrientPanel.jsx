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

// ── Reference daily values (adult male, FDA/NIH) ──────────────────────────
// Used only for progress bar rendering — not enforced.
const RDV = {
  // Vitamins
  vitamin_a_mcg:       900,
  vitamin_c_mg:        90,
  vitamin_d_mcg:       20,
  vitamin_e_mg:        15,
  vitamin_k_mcg:       120,
  thiamine_mg:         1.2,
  riboflavin_mg:       1.3,
  niacin_mg:           16,
  pantothenic_acid_mg: 5,
  pyridoxine_mg:       1.7,
  cobalamin_mcg:       2.4,
  biotin_mcg:          30,
  folate_mcg:          400,
  choline_mg:          550,
  // Minerals
  calcium_mg:   1000,
  iron_mg:      8,
  magnesium_mg: 420,
  phosphorus_mg:700,
  potassium_mg: 4700,
  zinc_mg:      11,
  copper_mg:    0.9,
  manganese_mg: 2.3,
  selenium_mcg: 55,
  chromium_mcg: 35,
  iodine_mcg:   150,
  molybdenum_mcg:45,
  fluoride_mg:  4,
  // Amino acids — no standard DRVs, use a rough per-kg adult estimate (70kg)
  histidine_g:    1.05,
  isoleucine_g:   1.40,
  leucine_g:      2.73,
  lysine_g:       2.10,
  methionine_g:   1.05,  // + cystine
  phenylalanine_g:1.75,  // + tyrosine
  threonine_g:    1.05,
  tryptophan_g:   0.28,
  valine_g:       1.82,
  // Fatty acids
  omega3_ala_g:  1.6,
  omega3_epa_g:  0.25,
  omega3_dha_g:  0.25,
  // Carb details
  fiber_g:         38,
  soluble_fiber_g: 10,
  caffeine_mg:     400,  // upper safe limit
  alcohol_g:       14,   // one standard drink
};

// ── Nutrient group definitions ─────────────────────────────────────────────
const GROUPS = [
  {
    key: "vitamins",
    label: "Vitamins",
    color: "#AF52DE",
    items: [
      { key: "vitamin_a_mcg",       label: "Vitamin A",         unit: "mcg" },
      { key: "vitamin_c_mg",        label: "Vitamin C",         unit: "mg"  },
      { key: "vitamin_d_mcg",       label: "Vitamin D",         unit: "mcg" },
      { key: "vitamin_e_mg",        label: "Vitamin E",         unit: "mg"  },
      { key: "vitamin_k_mcg",       label: "Vitamin K",         unit: "mcg" },
      { key: "thiamine_mg",         label: "B1 · Thiamine",     unit: "mg"  },
      { key: "riboflavin_mg",       label: "B2 · Riboflavin",   unit: "mg"  },
      { key: "niacin_mg",           label: "B3 · Niacin",       unit: "mg"  },
      { key: "pantothenic_acid_mg", label: "B5 · Pantothenic",  unit: "mg"  },
      { key: "pyridoxine_mg",       label: "B6 · Pyridoxine",   unit: "mg"  },
      { key: "cobalamin_mcg",       label: "B12 · Cobalamin",   unit: "mcg" },
      { key: "biotin_mcg",          label: "Biotin",            unit: "mcg" },
      { key: "folate_mcg",          label: "Folate",            unit: "mcg" },
      { key: "choline_mg",          label: "Choline",           unit: "mg"  },
      { key: "retinol_mcg",         label: "Retinol",           unit: "mcg" },
      { key: "alpha_carotene_mcg",  label: "α-Carotene",        unit: "mcg" },
      { key: "beta_carotene_mcg",   label: "β-Carotene",        unit: "mcg" },
      { key: "beta_cryptoxanthin_mcg", label: "β-Cryptoxanthin",unit: "mcg" },
      { key: "lutein_zeaxanthin_mcg",  label: "Lutein+Zeaxanthin",unit:"mcg"},
      { key: "lycopene_mcg",        label: "Lycopene",          unit: "mcg" },
      { key: "beta_tocopherol_mg",  label: "β-Tocopherol",      unit: "mg"  },
      { key: "delta_tocopherol_mg", label: "δ-Tocopherol",      unit: "mg"  },
      { key: "gamma_tocopherol_mg", label: "γ-Tocopherol",      unit: "mg"  },
    ],
  },
  {
    key: "minerals",
    label: "Minerals",
    color: "#FF9500",
    items: [
      { key: "calcium_mg",     label: "Calcium",    unit: "mg"  },
      { key: "iron_mg",        label: "Iron",       unit: "mg"  },
      { key: "magnesium_mg",   label: "Magnesium",  unit: "mg"  },
      { key: "phosphorus_mg",  label: "Phosphorus", unit: "mg"  },
      { key: "zinc_mg",        label: "Zinc",       unit: "mg"  },
      { key: "copper_mg",      label: "Copper",     unit: "mg"  },
      { key: "manganese_mg",   label: "Manganese",  unit: "mg"  },
      { key: "selenium_mcg",   label: "Selenium",   unit: "mcg" },
      { key: "chromium_mcg",   label: "Chromium",   unit: "mcg" },
      { key: "iodine_mcg",     label: "Iodine",     unit: "mcg" },
      { key: "molybdenum_mcg", label: "Molybdenum", unit: "mcg" },
      { key: "fluoride_mg",    label: "Fluoride",   unit: "mg"  },
    ],
  },
  {
    key: "amino_acids",
    label: "Amino Acids",
    color: "#34C759",
    items: [
      { key: "alanine_g",       label: "Alanine",       unit: "g" },
      { key: "arginine_g",      label: "Arginine",      unit: "g" },
      { key: "aspartic_acid_g", label: "Aspartic acid", unit: "g" },
      { key: "cystine_g",       label: "Cystine",       unit: "g" },
      { key: "glutamic_acid_g", label: "Glutamic acid", unit: "g" },
      { key: "glycine_g",       label: "Glycine",       unit: "g" },
      { key: "histidine_g",     label: "Histidine",     unit: "g" },
      { key: "hydroxyproline_g",label: "Hydroxyproline",unit: "g" },
      { key: "isoleucine_g",    label: "Isoleucine",    unit: "g" },
      { key: "leucine_g",       label: "Leucine",       unit: "g" },
      { key: "lysine_g",        label: "Lysine",        unit: "g" },
      { key: "methionine_g",    label: "Methionine",    unit: "g" },
      { key: "phenylalanine_g", label: "Phenylalanine", unit: "g" },
      { key: "proline_g",       label: "Proline",       unit: "g" },
      { key: "serine_g",        label: "Serine",        unit: "g" },
      { key: "threonine_g",     label: "Threonine",     unit: "g" },
      { key: "tryptophan_g",    label: "Tryptophan",    unit: "g" },
      { key: "tyrosine_g",      label: "Tyrosine",      unit: "g" },
      { key: "valine_g",        label: "Valine",        unit: "g" },
    ],
  },
  {
    key: "fatty_acids",
    label: "Fatty Acids",
    color: "#FF3B30",
    items: [
      { key: "monounsaturated_fat_g", label: "Monounsaturated", unit: "g" },
      { key: "polyunsaturated_fat_g", label: "Polyunsaturated", unit: "g" },
      { key: "omega3_ala_g",          label: "Omega-3 ALA",     unit: "g" },
      { key: "omega3_epa_g",          label: "Omega-3 EPA",     unit: "g" },
      { key: "omega3_dha_g",          label: "Omega-3 DHA",     unit: "g" },
      { key: "omega6_la_g",           label: "Omega-6 LA",      unit: "g" },
      { key: "omega6_aa_g",           label: "Omega-6 AA",      unit: "g" },
      { key: "phytosterol_mg",        label: "Phytosterols",    unit: "mg"},
    ],
  },
  {
    key: "carb_details",
    label: "Carb Details & Other",
    color: "#007AFF",
    items: [
      { key: "soluble_fiber_g",       label: "Soluble Fiber",   unit: "g"  },
      { key: "insoluble_fiber_g",     label: "Insoluble Fiber", unit: "g"  },
      { key: "fructose_g",            label: "Fructose",        unit: "g"  },
      { key: "galactose_g",           label: "Galactose",       unit: "g"  },
      { key: "glucose_g",             label: "Glucose",         unit: "g"  },
      { key: "lactose_g",             label: "Lactose",         unit: "g"  },
      { key: "maltose_g",             label: "Maltose",         unit: "g"  },
      { key: "sucrose_g",             label: "Sucrose",         unit: "g"  },
      { key: "oxalate_mg",            label: "Oxalate",         unit: "mg" },
      { key: "phytate_mg",            label: "Phytate",         unit: "mg" },
      { key: "caffeine_mg",           label: "Caffeine",        unit: "mg" },
      { key: "water_g",               label: "Water",           unit: "g"  },
      { key: "ash_g",                 label: "Ash",             unit: "g"  },
      { key: "alcohol_g",             label: "Alcohol",         unit: "g"  },
      { key: "beta_hydroxybutyrate_g",label: "β-Hydroxybutyrate",unit:"g" },
    ],
  },
];

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

  const formatVal = (v) => {
    if (v == null) return "—";
    if (v < 0.1)   return v.toFixed(3);
    if (v < 10)    return v.toFixed(2);
    if (v < 100)   return v.toFixed(1);
    return v.toFixed(0);
  };

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
