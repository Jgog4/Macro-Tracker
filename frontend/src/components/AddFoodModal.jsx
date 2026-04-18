/**
 * Add Food modal — unified search across Local, Restaurant, and USDA.
 * One search box, results from all sources with a source badge on each.
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, mealsApi } from "../api/client";
import { X, Search, Loader2, ChevronRight } from "lucide-react";

const SOURCE_BADGE = {
  restaurant: { label: "Restaurant", color: "bg-orange-500/20 text-orange-400" },
  usda:       { label: "USDA",       color: "bg-blue-500/20 text-blue-400" },
  custom:     { label: "Custom",     color: "bg-purple-500/20 text-purple-400" },
  usda_live:  { label: "USDA",       color: "bg-blue-500/20 text-blue-400" },
};

export default function AddFoodModal({ dateStr, defaultMealNumber, onClose, onLogged }) {
  const [query, setQuery]       = useState("");
  const [results, setResults]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [selected, setSelected] = useState(null);
  const [qty, setQty]           = useState("");
  const [logging, setLogging]   = useState(false);
  const [error, setError]       = useState("");
  const inputRef  = useRef();
  const searchGen = useRef(0); // incremented each time a search fires; stale callbacks are dropped

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Unified search across all sources
  useEffect(() => {
    // Increment on EVERY query change so any in-flight fetch is invalidated immediately
    const gen = ++searchGen.current;

    if (!query || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    const timer = setTimeout(async () => {
      // Another keystroke may have fired since we were scheduled — bail if stale
      if (gen !== searchGen.current) return;

      setLoading(true);
      try {
        const [localRes, usdaRes] = await Promise.allSettled([
          foodsApi.search(query, { limit: 20 }),
          foodsApi.usdaSearch(query, 5),
        ]);

        if (gen !== searchGen.current) return;

        const localItems = localRes.status === "fulfilled"
          ? localRes.value.data
          : [];

        const usdaItems = usdaRes.status === "fulfilled"
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

        const localFdcIds = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
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

      // If it's a live USDA result, import it first to get a local ID
      if (!ingredient_id && selected.fdc_id) {
        const imported = await foodsApi.importUsda(selected.fdc_id);
        ingredient_id = imported.data.id;
      }

      await mealsApi.logFood({
        log_date:    dateStr,
        meal_number: defaultMealNumber ?? undefined,
        items: [{ ingredient_id, quantity_g: parseFloat(qty) }],
      });
      onLogged();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to log food");
    } finally {
      setLogging(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Add Food">

      {/* Search box */}
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
          <button onClick={() => { setQuery(""); setSelected(null); setResults([]); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-white">
            <X size={13} />
          </button>
        )}
      </div>

      {/* Results list */}
      {!selected && (
        <div className="max-h-72 overflow-y-auto flex flex-col gap-0.5 -mx-1 px-1">
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
                    <p className="text-[11px] text-muted truncate">{food.brand}{food.serving_size_desc ? ` · ${food.serving_size_desc}` : ""}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 ml-3 shrink-0">
                  {food.calories != null && (
                    <span className="text-xs font-mono text-subtle">{Math.round(food.calories)} kcal</span>
                  )}
                  <ChevronRight size={14} className="text-muted group-hover:text-white transition-colors" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Selected item — quantity entry */}
      {selected && (
        <div className="flex flex-col gap-4">
          <button onClick={() => setSelected(null)}
            className="text-xs text-accent-blue hover:underline self-start flex items-center gap-1">
            ← Back to results
          </button>

          <div className="card-sm">
            <p className="text-sm font-semibold leading-snug">{selected.name}</p>
            {selected.brand && <p className="text-xs text-muted mt-0.5">{selected.brand}</p>}
            <div className="flex gap-5 mt-3">
              <MacroStat label="Cal"  value={selected.calories}  unit="kcal" color="text-accent-orange" />
              <MacroStat label="P"    value={selected.protein_g} unit="g"    color="text-accent-green" />
              <MacroStat label="C"    value={selected.carbs_g}   unit="g"    color="text-accent-blue" />
              <MacroStat label="F"    value={selected.fat_g}     unit="g"    color="text-accent-red" />
            </div>
            <p className="text-[11px] text-muted mt-1.5">
              Per {selected.serving_size_desc || "serving"}
            </p>
          </div>

          <div>
            <label className="text-xs text-subtle mb-1 block">Quantity (grams)</label>
            <input
              type="number"
              value={qty}
              onChange={e => setQty(e.target.value)}
              className="input font-mono"
              placeholder="100"
              min="1"
              step="0.5"
              autoFocus
            />
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <button
            onClick={handleLog}
            disabled={logging || !qty}
            className="btn-primary flex items-center justify-center gap-2 w-full py-3 disabled:opacity-50">
            {logging && <Loader2 size={14} className="animate-spin" />}
            Log to {defaultMealNumber ? `Meal ${defaultMealNumber}` : "New Meal"}
          </button>
        </div>
      )}
    </ModalShell>
  );
}

function MacroStat({ label, value, unit, color }) {
  return (
    <div className="flex flex-col">
      <span className={`text-sm font-bold font-mono ${color}`}>
        {value != null ? (value % 1 === 0 ? value : value.toFixed(1)) : "–"}
      </span>
      <span className="text-[10px] text-muted">{label} {unit}</span>
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
