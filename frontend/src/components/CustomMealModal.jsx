/**
 * Custom Meal Builder modal.
 * Build a meal from multiple ingredients with live macro totals.
 * Can log directly as Meal N, or save as a named Recipe.
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, mealsApi, recipesApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { Search, Loader2, ChevronRight, X, Plus, Trash2, BookmarkPlus, Check } from "lucide-react";

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

export default function CustomMealModal({ dateStr, defaultMealNumber, onClose, onLogged }) {
  // Search state
  const [query, setQuery]     = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const searchGen = useRef(0);

  // Basket state
  const [basket, setBasket]   = useState([]);   // {key, food, qty}
  const basketCounter = useRef(0);

  // Log settings
  const [mealNumber, setMealNumber] = useState(defaultMealNumber ?? 1);
  const [time, setTime]             = useState(nowTimeStr);
  const [logging, setLogging]       = useState(false);
  const [logError, setLogError]     = useState("");

  // Recipe save state
  const [recipePrompt, setRecipePrompt] = useState(false);
  const [recipeName, setRecipeName]     = useState("");
  const [savingRecipe, setSavingRecipe] = useState(false);
  const recipeInputRef = useRef();

  const inputRef = useRef();

  useEffect(() => { inputRef.current?.focus(); }, []);

  // ── Search ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    const gen = ++searchGen.current;
    if (!query || query.length < 2) { setResults([]); setSearching(false); return; }

    const timer = setTimeout(async () => {
      if (gen !== searchGen.current) return;
      setSearching(true);
      try {
        const [localRes, usdaRes] = await Promise.allSettled([
          foodsApi.search(query, { limit: 15 }),
          foodsApi.usdaSearch(query, 4),
        ]);
        if (gen !== searchGen.current) return;

        const localItems = localRes.status === "fulfilled" ? localRes.value.data : [];
        const usdaItems  = usdaRes.status  === "fulfilled"
          ? usdaRes.value.data.map(f => ({
              id:             null,
              fdc_id:         f.fdc_id,
              source:         "usda_live",
              name:           f.description,
              brand:          f.brand_owner,
              calories:       f.calories,
              protein_g:      f.protein_g,
              fat_g:          f.fat_g,
              carbs_g:        f.carbs_g,
              serving_size_g: f.serving_unit?.toLowerCase() === "g" ? f.serving_size : null,
            }))
          : [];

        const localFdcIds  = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
        const filteredUsda = usdaItems.filter(i => !localFdcIds.has(i.fdc_id));
        setResults([...localItems, ...filteredUsda]);
      } catch {
        if (gen !== searchGen.current) return;
        setResults([]);
      } finally {
        if (gen === searchGen.current) setSearching(false);
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  // ── Add to basket ──────────────────────────────────────────────────────────
  const addToBasket = (food) => {
    const defaultQty = food.serving_size_g ? String(food.serving_size_g) : "100";
    setBasket(b => [...b, { key: ++basketCounter.current, food, qty: defaultQty }]);
    setQuery("");
    setResults([]);
  };

  const updateQty = (key, qty) => {
    setBasket(b => b.map(item => item.key === key ? { ...item, qty } : item));
  };

  const removeFromBasket = (key) => {
    setBasket(b => b.filter(item => item.key !== key));
  };

  // ── Live totals ────────────────────────────────────────────────────────────
  const totals = basket.reduce((acc, { food, qty }) => {
    const qtyNum = parseFloat(qty) || 0;
    const baseG  = food.serving_size_g || (qtyNum || 100);
    const ratio  = qtyNum / baseG;
    acc.calories += (food.calories  || 0) * ratio;
    acc.protein  += (food.protein_g || 0) * ratio;
    acc.carbs    += (food.carbs_g   || 0) * ratio;
    acc.fat      += (food.fat_g     || 0) * ratio;
    return acc;
  }, { calories: 0, protein: 0, carbs: 0, fat: 0 });

  // ── Log as meal ────────────────────────────────────────────────────────────
  const handleLog = async () => {
    if (basket.length === 0) return;
    setLogging(true);
    setLogError("");
    try {
      // Import any USDA live items first
      const items = await Promise.all(
        basket.map(async ({ food, qty }) => {
          let ingredient_id = food.id;
          if (!ingredient_id && food.fdc_id) {
            const imported = await foodsApi.importUsda(food.fdc_id);
            ingredient_id = imported.data.id;
          }
          return { ingredient_id, quantity_g: parseFloat(qty) };
        })
      );

      const [h, m]   = time.split(":").map(Number);
      const loggedAt = new Date(`${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`);

      await mealsApi.logFood({
        log_date:    dateStr,
        meal_number: mealNumber,
        logged_at:   loggedAt.toISOString(),
        items,
      });
      onLogged();
    } catch (e) {
      setLogError(e.response?.data?.detail || "Failed to log meal");
    } finally {
      setLogging(false);
    }
  };

  // ── Save as recipe ─────────────────────────────────────────────────────────
  const handleSaveRecipe = async () => {
    if (!recipeName.trim() || basket.length === 0) return;
    setSavingRecipe(true);
    try {
      // Import any USDA live items first
      const ingredients = await Promise.all(
        basket.map(async ({ food, qty }) => {
          let ingredient_id = food.id;
          if (!ingredient_id && food.fdc_id) {
            const imported = await foodsApi.importUsda(food.fdc_id);
            ingredient_id = imported.data.id;
          }
          return { ingredient_id, quantity_g: parseFloat(qty) };
        })
      );

      await recipesApi.create({ name: recipeName.trim(), ingredients });
      setRecipePrompt(false);
      setRecipeName("");
    } catch (e) {
      setLogError(e.response?.data?.detail || "Failed to save recipe");
    } finally {
      setSavingRecipe(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <ModalShell onClose={onClose} title="Build Meal">

      {/* ── Search ── */}
      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search ingredients to add…"
          className="input pl-8"
        />
        {query && (
          <button onClick={() => { setQuery(""); setResults([]); }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-white">
            <X size={13} />
          </button>
        )}
      </div>

      {/* ── Search results dropdown ── */}
      {query.length >= 2 && (
        <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5 -mx-1 px-1 -mt-2">
          {searching ? (
            <div className="flex justify-center py-6">
              <Loader2 size={18} className="animate-spin text-muted" />
            </div>
          ) : results.length === 0 ? (
            <p className="text-center text-muted text-xs py-4">No results</p>
          ) : results.map((food, i) => {
            const badge = SOURCE_BADGE[food.source] || SOURCE_BADGE.custom;
            return (
              <button key={food.id || food.fdc_id || i}
                onClick={() => addToBasket(food)}
                className="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-surface-3 text-left transition-colors group w-full">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm text-white truncate">{food.name}</p>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${badge.color}`}>
                      {badge.label}
                    </span>
                  </div>
                  {food.brand && <p className="text-[11px] text-muted truncate">{food.brand}</p>}
                </div>
                <div className="flex items-center gap-2 ml-2 shrink-0">
                  {food.calories != null && (
                    <span className="text-xs font-mono text-subtle">{Math.round(food.calories)} kcal</span>
                  )}
                  <Plus size={14} className="text-muted group-hover:text-accent-blue transition-colors" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* ── Basket ── */}
      {basket.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-[10px] text-subtle uppercase tracking-wider px-1">Ingredients</p>
          {basket.map(({ key, food, qty }) => {
            const qtyNum = parseFloat(qty) || 0;
            const baseG  = food.serving_size_g || (qtyNum || 100);
            const ratio  = qtyNum / baseG;
            const kcal   = ((food.calories || 0) * ratio).toFixed(0);
            return (
              <div key={key} className="flex items-center gap-2 px-3 py-2 bg-surface-2 rounded-lg">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{food.name}</p>
                  {food.brand && <p className="text-[10px] text-muted truncate">{food.brand}</p>}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <input
                    type="number"
                    value={qty}
                    onChange={e => updateQty(key, e.target.value)}
                    className="input w-16 text-sm font-mono py-0.5 px-2 text-right"
                    min="0.5"
                    step="0.5"
                  />
                  <span className="text-[11px] text-muted">g</span>
                  <span className="text-[11px] font-mono text-subtle w-14 text-right">{kcal} kcal</span>
                  <button onClick={() => removeFromBasket(key)}
                    className="p-1 rounded hover:bg-red-500/20 text-muted hover:text-red-400">
                    <Trash2 size={11} />
                  </button>
                </div>
              </div>
            );
          })}

          {/* ── Live totals ── */}
          <div className="bg-surface-2 border border-border rounded-xl p-3 mt-1">
            <div className="grid grid-cols-4 gap-2">
              <TotalMacro label="Calories" value={totals.calories} unit="kcal" color="text-accent-orange" />
              <TotalMacro label="Protein"  value={totals.protein}  unit="g"    color="text-accent-green" />
              <TotalMacro label="Carbs"    value={totals.carbs}    unit="g"    color="text-accent-blue" />
              <TotalMacro label="Fat"      value={totals.fat}      unit="g"    color="text-accent-red" />
            </div>
          </div>
        </div>
      )}

      {/* ── Meal number + time (shown when basket has items) ── */}
      {basket.length > 0 && !recipePrompt && (
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="text-xs text-subtle mb-1.5 block">Meal</label>
            <div className="flex gap-1">
              {[1, 2, 3, 4, 5, 6].map(n => (
                <button key={n} onClick={() => setMealNumber(n)}
                  className={`flex-1 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
                    n === mealNumber ? "bg-accent-blue text-white" : "bg-surface-3 text-muted hover:text-white"
                  }`}>
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div className="w-28">
            <label className="text-xs text-subtle mb-1.5 block">Time</label>
            <input
              type="time"
              value={time}
              onChange={e => setTime(e.target.value)}
              className="input font-mono w-full"
            />
          </div>
        </div>
      )}

      {/* ── Recipe name prompt ── */}
      {recipePrompt && (
        <div className="flex items-center gap-2">
          <input
            ref={recipeInputRef}
            value={recipeName}
            onChange={e => setRecipeName(e.target.value)}
            placeholder="Recipe name…"
            className="input flex-1"
            autoFocus
            onKeyDown={e => {
              if (e.key === "Enter") handleSaveRecipe();
              if (e.key === "Escape") { setRecipePrompt(false); setRecipeName(""); }
            }}
          />
          <button
            onClick={handleSaveRecipe}
            disabled={savingRecipe || !recipeName.trim()}
            className="btn-primary py-2 px-3 flex items-center gap-1 text-sm">
            {savingRecipe ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            Save
          </button>
          <button onClick={() => { setRecipePrompt(false); setRecipeName(""); }}
            className="p-2 rounded hover:bg-surface-3 text-muted hover:text-white">
            <X size={14} />
          </button>
        </div>
      )}

      {logError && <p className="text-red-400 text-xs">{logError}</p>}

      {/* ── Actions ── */}
      {basket.length > 0 && !recipePrompt && (
        <div className="flex gap-2">
          <button
            onClick={() => { setRecipePrompt(true); setTimeout(() => recipeInputRef.current?.focus(), 50); }}
            className="btn-ghost flex items-center gap-1.5 px-4">
            <BookmarkPlus size={14} /> Save recipe
          </button>
          <button
            onClick={handleLog}
            disabled={logging || basket.some(b => !parseFloat(b.qty))}
            className="btn-primary flex-1 flex items-center justify-center gap-2 py-3 disabled:opacity-50">
            {logging && <Loader2 size={14} className="animate-spin" />}
            Log as Meal {mealNumber}
          </button>
        </div>
      )}

      {basket.length === 0 && query.length < 2 && (
        <p className="text-center text-muted text-sm py-2">
          Search for ingredients above to build your meal
        </p>
      )}
    </ModalShell>
  );
}

function TotalMacro({ label, value, unit, color }) {
  const display = value >= 10 ? Math.round(value) : value.toFixed(1);
  return (
    <div className="flex flex-col items-center">
      <span className={`text-base font-bold font-mono ${color}`}>{display}</span>
      <span className="text-[10px] text-muted mt-0.5">{unit}</span>
      <span className="text-[9px] text-subtle">{label}</span>
    </div>
  );
}
