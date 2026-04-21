/**
 * Add Food modal — search + entry screen.
 * Entry screen: meal selector (1–6), time picker, quantity with live macro preview.
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, mealsApi } from "../api/client";
import { X, Search, Loader2, ChevronRight, ChevronLeft } from "lucide-react";

const SOURCE_BADGE = {
  personal:   { label: "My Foods",   color: "bg-green-500/20 text-green-400" },
  restaurant: { label: "Restaurant", color: "bg-orange-500/20 text-orange-400" },
  usda:       { label: "USDA",       color: "bg-blue-500/20 text-blue-400" },
  custom:     { label: "Custom",     color: "bg-purple-500/20 text-purple-400" },
  usda_live:  { label: "USDA",       color: "bg-blue-500/20 text-blue-400" },
};

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export default function AddFoodModal({ dateStr, defaultMealNumber, onClose, onLogged }) {
  const [query, setQuery]           = useState("");
  const [results, setResults]       = useState([]);
  const [loading, setLoading]       = useState(false);
  const [selected, setSelected]     = useState(null);
  const [qty, setQty]               = useState("");
  const [mealNumber, setMealNumber] = useState(defaultMealNumber ?? 1);
  const [time, setTime]             = useState(nowTimeStr);
  const [logging, setLogging]       = useState(false);
  const [error, setError]           = useState("");

  const inputRef  = useRef();
  const qtyRef    = useRef();
  const searchGen = useRef(0);

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Focus qty input when a food is selected
  useEffect(() => {
    if (selected) setTimeout(() => qtyRef.current?.focus(), 50);
  }, [selected]);

  // ── Unified search ──────────────────────────────────────────────────────────
  useEffect(() => {
    const gen = ++searchGen.current;
    if (!query || query.length < 2) { setResults([]); setLoading(false); return; }

    const timer = setTimeout(async () => {
      if (gen !== searchGen.current) return;
      setLoading(true);
      try {
        const [localRes, usdaRes] = await Promise.allSettled([
          foodsApi.search(query, { limit: 20 }),
          foodsApi.usdaSearch(query, 5),
        ]);
        if (gen !== searchGen.current) return;

        const localItems = localRes.status === "fulfilled" ? localRes.value.data : [];
        const usdaItems  = usdaRes.status  === "fulfilled"
          ? usdaRes.value.data.map(f => ({
              id:                null,
              fdc_id:            f.fdc_id,
              source:            "usda_live",
              name:              f.description,
              brand:             f.brand_owner,
              calories:          f.calories,
              protein_g:         f.protein_g,
              fat_g:             f.fat_g,
              carbs_g:           f.carbs_g,
              serving_size_desc: f.serving_unit ? `${f.serving_size} ${f.serving_unit}` : null,
              serving_size_g:    f.serving_unit?.toLowerCase() === "g" ? f.serving_size : null,
            }))
          : [];

        const localFdcIds  = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
        const filteredUsda = usdaItems.filter(i => !localFdcIds.has(i.fdc_id));
        setResults([...localItems, ...filteredUsda]);
      } catch {
        if (gen !== searchGen.current) return;
        setResults([]);
      } finally {
        if (gen === searchGen.current) setLoading(false);
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  // ── Live macro calculation ──────────────────────────────────────────────────
  const qtyNum = parseFloat(qty) || 0;
  const baseG  = selected?.serving_size_g || (qtyNum || 100);
  const ratio  = qtyNum / baseG;
  const live   = selected ? {
    calories: (selected.calories  || 0) * ratio,
    protein:  (selected.protein_g || 0) * ratio,
    carbs:    (selected.carbs_g   || 0) * ratio,
    fat:      (selected.fat_g     || 0) * ratio,
  } : null;

  // ── Handlers ────────────────────────────────────────────────────────────────
  const handleSelect = (food) => {
    setSelected(food);
    setQty(food.serving_size_g ? String(food.serving_size_g) : "100");
    setError("");
  };

  const handleLog = async () => {
    if (!selected || !qty) return;
    setLogging(true);
    setError("");
    try {
      let ingredient_id = selected.id;
      if (!ingredient_id && selected.fdc_id) {
        const imported = await foodsApi.importUsda(selected.fdc_id);
        ingredient_id = imported.data.id;
      }

      // Build the logged_at ISO string from dateStr + time picker
      const [h, m]  = time.split(":").map(Number);
      const loggedAt = new Date(`${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`);

      await mealsApi.logFood({
        log_date:    dateStr,
        meal_number: mealNumber,
        logged_at:   loggedAt.toISOString(),
        items: [{ ingredient_id, quantity_g: parseFloat(qty) }],
      });
      onLogged();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to log food");
    } finally {
      setLogging(false);
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <ModalShell onClose={onClose} title={selected ? "Log Food" : "Add Food"}>

      {/* ── Search box (always visible) ── */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setSelected(null); }}
          placeholder="Search foods, restaurants, or ingredients…"
          className="input pl-8"
        />
        {query && (
          <button
            onClick={() => { setQuery(""); setSelected(null); setResults([]); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-white">
            <X size={13} />
          </button>
        )}
      </div>

      {/* ── Results list ── */}
      {!selected && (
        <div className="max-h-64 overflow-y-auto flex flex-col gap-0.5 -mx-1 px-1">
          {loading ? (
            <div className="flex justify-center py-10">
              <Loader2 size={20} className="animate-spin text-muted" />
            </div>
          ) : query.length < 2 ? (
            <p className="text-center text-muted text-sm py-10">
              Type at least 2 characters to search
            </p>
          ) : results.length === 0 ? (
            <p className="text-center text-muted text-sm py-10">No results found</p>
          ) : results.map((food, i) => {
            const badge = SOURCE_BADGE[food.source] || SOURCE_BADGE.custom;
            return (
              <button key={food.id || food.fdc_id || i}
                onClick={() => handleSelect(food)}
                className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-surface-3 text-left transition-colors group w-full">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm text-white truncate">{food.name}</p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${badge.color}`}>
                      {badge.label}
                    </span>
                  </div>
                  {food.brand && (
                    <p className="text-[11px] text-muted truncate">
                      {food.brand}{food.serving_size_desc ? ` · ${food.serving_size_desc}` : ""}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1.5 ml-2 shrink-0">
                  {food.calories != null && (
                    <span className="text-xs font-mono text-subtle whitespace-nowrap">
                      {food.serving_size_g
                        ? Math.round(food.calories / food.serving_size_g * 100)
                        : Math.round(food.calories)
                      }<span className="text-[10px] ml-0.5 text-muted">cal/100g</span>
                    </span>
                  )}
                  <ChevronRight size={14} className="text-muted group-hover:text-white transition-colors shrink-0" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Entry screen (food selected) ── */}
      {selected && (
        <div className="flex flex-col gap-4">

          {/* Food name + back */}
          <div className="flex items-start gap-2">
            <button
              onClick={() => setSelected(null)}
              className="mt-0.5 p-1 rounded hover:bg-surface-3 text-muted hover:text-white transition-colors shrink-0">
              <ChevronLeft size={15} />
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold leading-snug">{selected.name}</p>
              {selected.brand && <p className="text-xs text-muted mt-0.5">{selected.brand}</p>}
            </div>
          </div>

          {/* Meal selector */}
          <div>
            <label className="text-xs text-subtle mb-1.5 block">Meal</label>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5, 6].map(n => (
                <button
                  key={n}
                  onClick={() => setMealNumber(n)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${
                    n === mealNumber
                      ? "bg-accent-blue text-white"
                      : "bg-surface-3 text-muted hover:text-white"
                  }`}>
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Quantity + Time row */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-subtle mb-1 block">Quantity (g)</label>
              <input
                ref={qtyRef}
                type="number"
                value={qty}
                onChange={e => setQty(e.target.value)}
                className="input font-mono w-full"
                placeholder="100"
                min="1"
                step="0.5"
              />
            </div>
            <div>
              <label className="text-xs text-subtle mb-1 block">Time</label>
              <input
                type="time"
                value={time}
                onChange={e => setTime(e.target.value)}
                className="input font-mono w-full"
              />
            </div>
          </div>

          {/* Live macro preview */}
          <div className="bg-surface-2 border border-border rounded-xl p-3">
            <div className="grid grid-cols-4 gap-2">
              <LiveMacro label="Calories" value={live?.calories} unit="kcal" color="text-accent-orange" />
              <LiveMacro label="Protein"  value={live?.protein}  unit="g"    color="text-accent-green" />
              <LiveMacro label="Carbs"    value={live?.carbs}    unit="g"    color="text-accent-blue" />
              <LiveMacro label="Fat"      value={live?.fat}      unit="g"    color="text-accent-red" />
            </div>
            <p className="text-[10px] text-muted mt-2 text-center">
              For {qtyNum > 0 ? `${qtyNum} g` : "—"} serving
              {selected.serving_size_g
                ? ` · per 100 g: ${Math.round((selected.calories || 0) / (selected.serving_size_g / 100))} kcal`
                : ""}
            </p>
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <button
            onClick={handleLog}
            disabled={logging || !qty || qtyNum <= 0}
            className="btn-primary flex items-center justify-center gap-2 w-full py-3 disabled:opacity-50">
            {logging && <Loader2 size={14} className="animate-spin" />}
            Log to Meal {mealNumber}
          </button>
        </div>
      )}
    </ModalShell>
  );
}

function LiveMacro({ label, value, unit, color }) {
  const display = value != null && !isNaN(value)
    ? (value >= 10 ? Math.round(value) : value.toFixed(1))
    : "—";
  return (
    <div className="flex flex-col items-center">
      <span className={`text-base font-bold font-mono ${color}`}>{display}</span>
      <span className="text-[10px] text-muted mt-0.5">{unit}</span>
      <span className="text-[9px] text-subtle">{label}</span>
    </div>
  );
}

export function ModalShell({ onClose, title, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full sm:max-w-md bg-surface-1 border border-border rounded-t-2xl sm:rounded-2xl p-5 flex flex-col gap-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-surface-3 text-muted hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
