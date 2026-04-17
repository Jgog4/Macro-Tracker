/**
 * Add Food modal — search local DB + USDA, select quantity, log to meal.
 * Tabs: Local | Restaurant | USDA
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, mealsApi } from "../api/client";
import { X, Search, Loader2, ChevronRight } from "lucide-react";

const TABS = ["Local", "Restaurant", "USDA"];
const BRANDS = ["Chipotle", "Cactus Club", "Pokerrito"];

export default function AddFoodModal({ dateStr, defaultMealNumber, onClose, onLogged }) {
  const [tab, setTab]           = useState("Local");
  const [query, setQuery]       = useState("");
  const [brand, setBrand]       = useState("");
  const [results, setResults]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [selected, setSelected] = useState(null);
  const [qty, setQty]           = useState("");
  const [logging, setLogging]   = useState(false);
  const [error, setError]       = useState("");
  const inputRef = useRef();

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Search
  useEffect(() => {
    if (!query && tab !== "Restaurant") { setResults([]); return; }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        let res;
        if (tab === "USDA") {
          res = await foodsApi.usdaSearch(query);
          setResults(res.data.map(f => ({
            id:           null,
            fdc_id:       f.fdc_id,
            name:         f.description,
            brand:        f.brand_owner,
            calories:     f.calories,
            protein_g:    f.protein_g,
            fat_g:        f.fat_g,
            carbs_g:      f.carbs_g,
            serving_size_desc: f.serving_unit ? `${f.serving_size} ${f.serving_unit}` : null,
          })));
        } else if (tab === "Restaurant") {
          res = await foodsApi.getRestaurant(brand || undefined);
          const items = res.data.filter(f =>
            !query || f.name.toLowerCase().includes(query.toLowerCase())
          );
          setResults(items);
        } else {
          res = await foodsApi.search(query);
          setResults(res.data);
        }
      } catch { setResults([]); }
      setLoading(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, tab, brand]);

  // Load restaurant items on mount
  useEffect(() => {
    if (tab === "Restaurant") {
      setLoading(true);
      foodsApi.getRestaurant(brand || undefined)
        .then(r => setResults(r.data))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }
  }, [tab, brand]);

  const handleSelect = (food) => {
    setSelected(food);
    setQty(food.serving_size_g ? String(food.serving_size_g) : "100");
  };

  const handleLog = async () => {
    if (!selected || !qty) return;
    setLogging(true);
    setError("");
    try {
      // If USDA item, import it first to get a local ID
      let ingredient_id = selected.id;
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
      {/* Tabs */}
      <div className="flex gap-1 mb-4 bg-surface-3 rounded-lg p-1">
        {TABS.map(t => (
          <button key={t} onClick={() => { setTab(t); setSelected(null); setResults([]); }}
            className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === t ? "bg-surface-1 text-white shadow" : "text-muted hover:text-white"}`}>
            {t}
          </button>
        ))}
      </div>

      {/* Brand filter for Restaurant tab */}
      {tab === "Restaurant" && (
        <div className="flex gap-1 mb-3 flex-wrap">
          {["", ...BRANDS].map(b => (
            <button key={b} onClick={() => setBrand(b)}
              className={`text-[11px] px-2.5 py-1 rounded-full border transition-colors ${brand === b ? "border-accent-blue text-accent-blue" : "border-border text-muted hover:border-subtle"}`}>
              {b || "All"}
            </button>
          ))}
        </div>
      )}

      {/* Search */}
      <div className="relative mb-3">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={tab === "USDA" ? "Search USDA database…" : "Search foods…"}
          className="input pl-8"
        />
      </div>

      {/* Results */}
      {!selected && (
        <div className="max-h-60 overflow-y-auto flex flex-col gap-1">
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-muted" /></div>
          ) : results.length === 0 ? (
            <p className="text-center text-muted text-sm py-8">{query ? "No results" : "Type to search"}</p>
          ) : results.map((food, i) => (
            <button key={food.id || food.fdc_id || i}
              onClick={() => handleSelect(food)}
              className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-surface-3 text-left transition-colors group">
              <div className="min-w-0">
                <p className="text-sm text-white truncate">{food.name}</p>
                <p className="text-[11px] text-muted">{food.brand && `${food.brand} · `}{food.serving_size_desc}</p>
              </div>
              <div className="flex items-center gap-3 ml-2 shrink-0">
                <span className="text-xs font-mono text-subtle">{(food.calories || 0).toFixed(0)} kcal</span>
                <ChevronRight size={14} className="text-muted group-hover:text-white" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Selected — quantity entry */}
      {selected && (
        <div className="flex flex-col gap-4">
          <button onClick={() => setSelected(null)} className="text-xs text-accent-blue hover:underline self-start">
            ← Back to results
          </button>

          <div className="card-sm">
            <p className="text-sm font-semibold">{selected.name}</p>
            {selected.brand && <p className="text-xs text-muted mt-0.5">{selected.brand}</p>}
            <div className="flex gap-4 mt-3">
              <Macro label="Cal"  value={selected.calories}  unit="kcal" color="text-accent-orange" />
              <Macro label="P"    value={selected.protein_g} unit="g"    color="text-accent-green" />
              <Macro label="C"    value={selected.carbs_g}   unit="g"    color="text-accent-blue" />
              <Macro label="F"    value={selected.fat_g}     unit="g"    color="text-accent-red" />
            </div>
            <p className="text-[11px] text-muted mt-1">Per {selected.serving_size_desc || "serving"}</p>
          </div>

          <div>
            <label className="text-xs text-subtle mb-1 block">Quantity (grams)</label>
            <input
              type="number" value={qty} onChange={e => setQty(e.target.value)}
              className="input font-mono" placeholder="100"
              min="1" step="0.5" autoFocus
            />
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <button onClick={handleLog} disabled={logging || !qty}
            className="btn-primary flex items-center justify-center gap-2 w-full py-3">
            {logging ? <Loader2 size={14} className="animate-spin" /> : null}
            Log to {defaultMealNumber ? `Meal ${defaultMealNumber}` : "New Meal"}
          </button>
        </div>
      )}
    </ModalShell>
  );
}

function Macro({ label, value, unit, color }) {
  return (
    <div className="flex flex-col">
      <span className={`text-sm font-bold font-mono ${color}`}>{(value || 0).toFixed(1)}</span>
      <span className="text-[10px] text-muted">{label} {unit}</span>
    </div>
  );
}

export function ModalShell({ onClose, title, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Sheet */}
      <div className="relative w-full sm:max-w-md bg-surface-1 border border-border rounded-t-2xl sm:rounded-2xl p-5 flex flex-col gap-4 max-h-[90vh] overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-surface-3 text-muted hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
