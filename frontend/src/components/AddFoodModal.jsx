/**
 * Add Food modal — search + entry screen (iOS light theme).
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, mealsApi, recipesApi } from "../api/client";
import { X, Search, Loader2, ChevronRight, ChevronLeft } from "lucide-react";

const SOURCE_BADGE = {
  personal:   { label: "My Foods",   color: "bg-green-100 text-green-700" },
  restaurant: { label: "Restaurant", color: "bg-orange-100 text-orange-700" },
  usda:       { label: "USDA",       color: "bg-blue-100 text-blue-700" },
  custom:     { label: "Custom",     color: "bg-purple-100 text-purple-700" },
  usda_live:  { label: "USDA",       color: "bg-blue-100 text-blue-700" },
  recipe:     { label: "Recipe",     color: "bg-emerald-100 text-emerald-700" },
};

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
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
  useEffect(() => { if (selected) setTimeout(() => qtyRef.current?.focus(), 50); }, [selected]);

  // Unified search (local + USDA + Recipes)
  useEffect(() => {
    const gen = ++searchGen.current;
    if (!query || query.length < 2) { setResults([]); setLoading(false); return; }
    const timer = setTimeout(async () => {
      if (gen !== searchGen.current) return;
      setLoading(true);
      try {
        const [localRes, usdaRes, recipesRes] = await Promise.allSettled([
          foodsApi.search(query, { limit: 20 }),
          foodsApi.usdaSearch(query, 5),
          recipesApi.search(query),
        ]);
        if (gen !== searchGen.current) return;
        const localItems = localRes.status === "fulfilled" ? localRes.value.data : [];
        const usdaItems  = usdaRes.status === "fulfilled"
          ? usdaRes.value.data.map(f => ({
              id: null, fdc_id: f.fdc_id, source: "usda_live",
              name: f.description, brand: f.brand_owner,
              calories: f.calories, protein_g: f.protein_g,
              fat_g: f.fat_g, carbs_g: f.carbs_g,
              serving_size_desc: f.serving_unit ? `${f.serving_size} ${f.serving_unit}` : null,
              serving_size_g: f.serving_unit?.toLowerCase() === "g" ? f.serving_size : null,
            }))
          : [];
        const recipeItems = recipesRes.status === "fulfilled"
          ? recipesRes.value.data.map(r => ({
              id: null, recipe_id: r.id, source: "recipe",
              name: r.name, brand: null,
              calories: r.calories, protein_g: r.protein_g,
              fat_g: r.fat_g, carbs_g: r.carbs_g,
              serving_size_g: r.serving_size_g || r.total_weight_g,
              serving_size_desc: r.serving_size_g ? `${r.serving_size_g}g cooked` : null,
            }))
          : [];
        const localFdcIds = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
        setResults([
          ...recipeItems,
          ...localItems,
          ...usdaItems.filter(i => !localFdcIds.has(i.fdc_id)),
        ]);
      } catch { if (gen === searchGen.current) setResults([]); }
      finally { if (gen === searchGen.current) setLoading(false); }
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  const qtyNum = parseFloat(qty) || 0;
  const baseG  = selected?.serving_size_g || (qtyNum || 100);
  const ratio  = qtyNum / baseG;
  const live   = selected ? {
    calories: (selected.calories  || 0) * ratio,
    protein:  (selected.protein_g || 0) * ratio,
    carbs:    (selected.carbs_g   || 0) * ratio,
    fat:      (selected.fat_g     || 0) * ratio,
  } : null;

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
      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(`${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`);
      let item;
      if (selected.recipe_id) {
        item = { recipe_id: selected.recipe_id, quantity_g: parseFloat(qty) };
      } else {
        let ingredient_id = selected.id;
        if (!ingredient_id && selected.fdc_id) {
          const imported = await foodsApi.importUsda(selected.fdc_id);
          ingredient_id = imported.data.id;
        }
        item = { ingredient_id, quantity_g: parseFloat(qty) };
      }
      await mealsApi.logFood({
        log_date: dateStr, meal_number: mealNumber,
        logged_at: loggedAt.toISOString(),
        items: [item],
      });
      onLogged();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to log food");
    } finally { setLogging(false); }
  };

  return (
    <ModalShell onClose={onClose} title={selected ? "Log Food" : "Add Food"}>

      {/* Search box */}
      <div className="relative w-full min-w-0">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => { setQuery(e.target.value); setSelected(null); }}
          placeholder="Search foods, restaurants, or ingredients…"
          className="input pl-8 w-full min-w-0"
        />
        {query && (
          <button onClick={() => { setQuery(""); setSelected(null); setResults([]); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground">
            <X size={13} />
          </button>
        )}
      </div>

      {/* Results list */}
      {!selected && (
        <div className="max-h-64 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 size={20} className="animate-spin text-muted" /></div>
          ) : query.length < 2 ? (
            <p className="text-center text-muted text-sm py-10">Type at least 2 characters to search</p>
          ) : results.length === 0 ? (
            <p className="text-center text-muted text-sm py-10">No results found</p>
          ) : results.map((food, i) => {
            const badge = SOURCE_BADGE[food.source] || SOURCE_BADGE.custom;
            return (
              <button key={food.id || food.fdc_id || i}
                onClick={() => handleSelect(food)}
                className="flex w-full items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-surface-2 text-left transition-colors">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <p className="text-sm text-foreground truncate">{food.name}</p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-semibold shrink-0 ${badge.color}`}>
                      {badge.label}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted mt-0.5 truncate">
                    {food.brand ? `${food.brand} · ` : ""}
                    {food.calories != null && (
                      `${food.serving_size_g
                        ? Math.round(food.calories / food.serving_size_g * 100)
                        : Math.round(food.calories)} cal/100g`
                    )}
                  </p>
                </div>
                <ChevronRight size={14} className="text-muted shrink-0" />
              </button>
            );
          })}
        </div>
      )}

      {/* Entry screen */}
      {selected && (
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-2">
            <button onClick={() => setSelected(null)}
              className="mt-0.5 p-1.5 rounded-lg hover:bg-surface-2 text-muted transition-colors shrink-0">
              <ChevronLeft size={15} />
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground leading-snug">{selected.name}</p>
              {selected.brand && <p className="text-xs text-muted mt-0.5">{selected.brand}</p>}
            </div>
          </div>

          {/* Meal selector */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">Meal</label>
            <div className="grid grid-cols-6 gap-1">
              {[1,2,3,4,5,6].map(n => (
                <button key={n} onClick={() => setMealNumber(n)}
                  className={`py-2 rounded-xl text-sm font-bold transition-colors
                    ${n === mealNumber ? "bg-accent-blue text-white shadow-sm" : "bg-surface-2 text-muted hover:bg-surface-3"}`}>
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Qty + Time */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Quantity (g)</label>
              <input ref={qtyRef} type="number" value={qty} onChange={e => setQty(e.target.value)}
                className="input font-mono" placeholder="100" min="1" step="0.5" />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Time</label>
              <input type="time" value={time} onChange={e => setTime(e.target.value)}
                className="input font-mono" />
            </div>
          </div>

          {/* Live macros */}
          <div className="bg-surface-2 rounded-2xl p-4">
            <div className="grid grid-cols-4 gap-2">
              <LiveMacro label="Calories" value={live?.calories} unit="kcal" color="#FF9500" />
              <LiveMacro label="Protein"  value={live?.protein}  unit="g"    color="#34C759" />
              <LiveMacro label="Carbs"    value={live?.carbs}    unit="g"    color="#007AFF" />
              <LiveMacro label="Fat"      value={live?.fat}      unit="g"    color="#FF3B30" />
            </div>
            <p className="text-[10px] text-muted mt-2 text-center">
              For {qtyNum > 0 ? `${qtyNum} g` : "—"} serving
              {selected.serving_size_g
                ? ` · per 100 g: ${Math.round((selected.calories || 0) / (selected.serving_size_g / 100))} kcal`
                : ""}
            </p>
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <button onClick={handleLog} disabled={logging || !qty || qtyNum <= 0}
            className="btn-primary flex items-center justify-center gap-2 w-full py-3.5 disabled:opacity-40">
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
      <span className="text-base font-bold font-mono" style={{ color }}>{display}</span>
      <span className="text-[10px] text-muted mt-0.5">{unit}</span>
      <span className="text-[9px] text-subtle">{label}</span>
    </div>
  );
}

export function ModalShell({ onClose, title, children }) {
  return (
    <>
      {/* Backdrop — fixed to the viewport so it always covers the whole screen */}
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />

      {/* Sheet — `fixed` binds it strictly to the device viewport, so it
          can't be pushed off-screen by a parent container that's
          accidentally wider than 100vw. max-w-md + mx-auto centers it on
          tablets, w-full + box-border guarantees 100% of the viewport
          width INCLUDING padding — never more. */}
      <div className="fixed bottom-0 left-0 right-0 w-full max-w-md mx-auto box-border z-50 overflow-hidden rounded-t-3xl shadow-2xl">
        {/* Only overflow-y here — setting overflow-x:hidden on the same element
            as overflow-y:auto triggers an iOS WebKit bug that converts hidden→auto. */}
        <div
          className="bg-white w-full min-w-0 box-border flex flex-col gap-4 overflow-y-auto px-4 pt-5"
          style={{
            maxHeight: "85dvh",
            paddingBottom: "calc(90px + env(safe-area-inset-bottom, 0px))",
          }}
        >
          {/* Handle */}
          <div className="w-9 h-1 rounded-full bg-surface-3 mx-auto shrink-0" />
          <div className="flex items-center justify-between gap-2 shrink-0 min-w-0">
            <h2 className="text-lg font-bold text-foreground min-w-0 truncate">{title}</h2>
            <button
              onClick={onClose}
              className="w-8 h-8 shrink-0 flex items-center justify-center rounded-full bg-surface-2 text-muted hover:bg-surface-3 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
          {children}
        </div>
      </div>
    </>
  );
}
