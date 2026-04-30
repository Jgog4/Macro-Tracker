/**
 * Add Food modal — search + entry screen (iOS light theme).
 *
 * Quantity entry uses the Cronometer pattern:
 *   [Amount input]  [Serving Size dropdown ▾]
 *
 * Serving Size options:
 *   - Named serving (e.g. "1 square — 22g") when the food has serving_size_g
 *   - "g" — always present; Amount becomes raw grams
 *
 * Logged quantity_g = amount × selectedOption.gramsEach
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { foodsApi, mealsApi, recipesApi } from "../api/client";
import { X, Search, Loader2, ChevronRight, ChevronLeft, ChevronDown } from "lucide-react";

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

/** Build the list of serving-size options for a food item.
 *  customG: optional override gram-weight entered by the user. */
function buildServingOptions(food, customG = null) {
  const options = [];

  const servingG = (customG && customG > 0) ? customG : food.serving_size_g;

  if (servingG) {
    const raw   = (food.serving_size_desc || "").trim();
    // Suppress ugly USDA unit codes like "22 GRM", "28.35 G", etc.
    const isRawGrams = /^\d+\.?\d*\s*(g|grm|gram|grams|gr|ml)$/i.test(raw);
    let label;
    if (customG && customG > 0) {
      label = "serving";                    // user-defined
    } else if (raw && !isRawGrams) {
      label = raw;                          // e.g. "1 bar", "1 cup"
    } else if (food.source === "recipe") {
      label = "full recipe";
    } else {
      label = "serving";
    }
    options.push({ id: "serving", label, gramsEach: servingG });
  }

  // "g" is always available — lets user enter any gram weight
  options.push({ id: "g", label: "g", gramsEach: 1 });

  return options;
}

export default function AddFoodModal({ dateStr, defaultMealNumber, onClose, onLogged, preselected = null, recipesOnly = false }) {
  const [query, setQuery]             = useState("");
  const [results, setResults]         = useState([]);
  const [loading, setLoading]         = useState(false);
  const [selected, setSelected]       = useState(null);
  const [amount, setAmount]           = useState("1");      // how many of the chosen unit
  const [servingOpts, setServingOpts] = useState([]);       // options array
  const [servingOpt, setServingOpt]   = useState(null);     // currently selected option
  const [showPicker, setShowPicker]   = useState(false);    // serving-size picker open?
  const [mealNumber, setMealNumber]   = useState(defaultMealNumber ?? 1);
  const [time, setTime]               = useState(nowTimeStr);
  const [logging, setLogging]         = useState(false);
  const [error, setError]             = useState("");
  // "Set item weight" feature — for foods with no serving_size_g
  const [itemWeightG, setItemWeightG] = useState("");       // user-typed gram weight per item
  const [saveToFood, setSaveToFood]   = useState(false);    // save weight back to DB?
  // Extra nutrition fields — shown when all core macros are zero
  const [customCal, setCustomCal]     = useState("");
  const [customPro, setCustomPro]     = useState("");
  const [customCarb, setCustomCarb]   = useState("");
  const [customFat, setCustomFat]     = useState("");

  const inputRef   = useRef();
  const amountRef  = useRef();
  const searchGen  = useRef(0);
  // mealTimes as state so React re-renders when the fetch completes
  const [mealTimes,    setMealTimes]    = useState({});
  const [timeEdited,   setTimeEdited]   = useState(false); // true once user manually changes time

  // Fetch today's meals once on open
  useEffect(() => {
    mealsApi.getDay(dateStr).then(res => {
      const map = {};
      (res.data?.meals || []).forEach(meal => {
        if (meal.logged_at) {
          const d = new Date(meal.logged_at);
          map[meal.meal_number] = `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
        }
      });
      setMealTimes(map);
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Whenever the selected meal OR the fetched times change, auto-fill the time
  // (skipped if the user has manually edited the time field)
  useEffect(() => {
    if (timeEdited) return;
    setTime(mealTimes[mealNumber] || nowTimeStr());
  }, [mealNumber, mealTimes]); // eslint-disable-line react-hooks/exhaustive-deps

  // Switching meals resets the "user edited" flag so the new meal gets auto-filled
  const handleMealChange = useCallback((n) => {
    setTimeEdited(false);
    setMealNumber(n);
  }, []);

  // If a food was pre-selected (e.g. just scanned from camera), skip search
  useEffect(() => {
    if (preselected) handleSelect(preselected);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // In recipesOnly mode, auto-load all recipes on open
  useEffect(() => {
    if (!recipesOnly) return;
    setLoading(true);
    recipesApi.list().then(res => {
      setResults(res.data.map(r => ({
        id: null, recipe_id: r.id, source: "recipe",
        name: r.name, brand: null,
        calories: r.calories, protein_g: r.protein_g,
        fat_g: r.fat_g, carbs_g: r.carbs_g,
        serving_size_g: r.serving_size_g || r.total_weight_g,
        serving_size_desc: r.serving_size_g ? `full recipe (${r.serving_size_g}g)` : null,
      })));
    }).catch(() => {}).finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recipesOnly]);

  useEffect(() => { if (!preselected) inputRef.current?.focus(); }, [preselected]);
  useEffect(() => {
    if (selected) setTimeout(() => amountRef.current?.focus(), 50);
  }, [selected]);

  // ── Unified search ────────────────────────────────────────────────────────
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
              serving_size_g: (() => {
                if (!f.serving_size || !f.serving_unit) return null;
                const u = f.serving_unit.toLowerCase().trim();
                if (["g","grm","gram","grams","gr"].includes(u)) return f.serving_size;
                if (["oz","ounce","ounces"].includes(u)) return Math.round(f.serving_size * 28.3495 * 10) / 10;
                if (["ml","milliliter","milliliters"].includes(u)) return f.serving_size;
                return null;
              })(),
            }))
          : [];
        const recipeItems = recipesRes.status === "fulfilled"
          ? recipesRes.value.data.map(r => ({
              id: null, recipe_id: r.id, source: "recipe",
              name: r.name, brand: null,
              calories: r.calories, protein_g: r.protein_g,
              fat_g: r.fat_g, carbs_g: r.carbs_g,
              serving_size_g: r.serving_size_g || r.total_weight_g,
              serving_size_desc: r.serving_size_g
                ? `full recipe (${r.serving_size_g}g)`
                : null,
            }))
          : [];
        const localFdcIds = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
        setResults([
          ...recipeItems,
          ...localItems,
          ...usdaItems.filter(i => !localFdcIds.has(i.fdc_id)),
        ]);
      } catch { if (gen === searchGen.current) setResults([]); }
      finally  { if (gen === searchGen.current) setLoading(false); }
    }, 350);
    return () => clearTimeout(timer);
  }, [query]);

  // ── Derived: grams that will be logged ───────────────────────────────────
  const amountNum = parseFloat(amount) || 0;
  const qtyNum    = amountNum * (servingOpt?.gramsEach ?? 1);

  // Effective serving base: prefer custom weight, then food's stored weight
  const effectiveServingG = (parseFloat(itemWeightG) > 0 ? parseFloat(itemWeightG) : null)
                         ?? selected?.serving_size_g;
  const baseG = effectiveServingG || (qtyNum || 100);
  const ratio = qtyNum / baseG;

  // Use custom-entered macros if the food has all zeros
  const allMacrosZero = selected && !selected.calories && !selected.protein_g && !selected.carbs_g && !selected.fat_g;
  const effCal  = allMacrosZero && customCal  ? parseFloat(customCal)  : (selected?.calories  || 0);
  const effPro  = allMacrosZero && customPro  ? parseFloat(customPro)  : (selected?.protein_g || 0);
  const effCarb = allMacrosZero && customCarb ? parseFloat(customCarb) : (selected?.carbs_g   || 0);
  const effFat  = allMacrosZero && customFat  ? parseFloat(customFat)  : (selected?.fat_g     || 0);

  const live  = selected ? {
    calories: effCal  * ratio,
    protein:  effPro  * ratio,
    carbs:    effCarb * ratio,
    fat:      effFat  * ratio,
  } : null;

  // ── When custom item weight changes, rebuild serving options live ────────
  // Only runs when itemWeightG actually changes (selected is stable once chosen)
  useEffect(() => {
    if (!selected || itemWeightG === "") return;   // "" = initial state, skip
    const customG = parseFloat(itemWeightG) > 0 ? parseFloat(itemWeightG) : null;
    const opts = buildServingOptions(selected, customG);
    setServingOpts(opts);
    if (customG) {
      setServingOpt(opts[0]);                       // named serving
      setAmount(a => (a === "100" ? "1" : a));
    } else {
      setServingOpt(opts[opts.length - 1]);         // "g"
      setAmount("100");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemWeightG]);

  // ── Select a food from results ────────────────────────────────────────────
  const handleSelect = (food) => {
    const opts = buildServingOptions(food);
    setSelected(food);
    setServingOpts(opts);
    setServingOpt(opts[0]);
    // Default amount: 1 for named servings, 100 for raw grams
    setAmount(opts[0].id === "g" ? "100" : "1");
    setShowPicker(false);
    setError("");
    // Reset "set item weight" fields
    setItemWeightG("");
    setSaveToFood(!!food.id);   // pre-tick save if food is already in our DB
    setCustomCal(""); setCustomPro(""); setCustomCarb(""); setCustomFat("");
  };

  // ── Log to diary ──────────────────────────────────────────────────────────
  const handleLog = async () => {
    if (!selected || qtyNum <= 0) return;
    setLogging(true);
    setError("");
    try {
      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(
        `${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`
      );
      let item;
      if (selected.recipe_id) {
        item = { recipe_id: selected.recipe_id, quantity_g: qtyNum };
      } else {
        let ingredient_id = selected.id;
        if (!ingredient_id && selected.fdc_id) {
          const imported = await foodsApi.importUsda(selected.fdc_id);
          ingredient_id = imported.data.id;
        }

        // Save item weight (and nutrition) back to the food if requested
        const customServingG = parseFloat(itemWeightG);
        if (saveToFood && customServingG > 0 && ingredient_id) {
          const patch = { serving_size_g: customServingG };
          if (allMacrosZero) {
            if (customCal)  patch.calories  = parseFloat(customCal);
            if (customPro)  patch.protein_g = parseFloat(customPro);
            if (customCarb) patch.carbs_g   = parseFloat(customCarb);
            if (customFat)  patch.fat_g     = parseFloat(customFat);
          }
          await foodsApi.update(ingredient_id, patch);
        }

        item = { ingredient_id, quantity_g: qtyNum };
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
    <ModalShell onClose={onClose} title={selected ? "Log Food" : recipesOnly ? "Log Recipe" : "Add Food"}>

      {/* ── Search box — hidden in recipesOnly mode ── */}
      {!recipesOnly && (
        <div className="relative w-full min-w-0">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setSelected(null); setShowPicker(false); }}
            placeholder="Search foods, restaurants, or ingredients…"
            className="input pl-8 w-full min-w-0"
          />
          {query && (
            <button
              onClick={() => { setQuery(""); setSelected(null); setResults([]); setShowPicker(false); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground"
            >
              <X size={13} />
            </button>
          )}
        </div>
      )}

      {/* ── Results list ── */}
      {!selected && (
        <div className="max-h-64 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-10">
              <Loader2 size={20} className="animate-spin text-muted" />
            </div>
          ) : recipesOnly && results.length === 0 ? (
            <p className="text-center text-muted text-sm py-10">No saved recipes yet — build one in the Library tab</p>
          ) : !recipesOnly && query.length < 2 ? (
            <p className="text-center text-muted text-sm py-10">Type at least 2 characters to search</p>
          ) : results.length === 0 ? (
            <p className="text-center text-muted text-sm py-10">No results found</p>
          ) : results.map((food, i) => {
            const badge = SOURCE_BADGE[food.source] || SOURCE_BADGE.custom;
            return (
              <button key={food.id || food.fdc_id || i}
                onClick={() => handleSelect(food)}
                className="flex w-full items-center gap-2 px-3 py-2.5 rounded-xl hover:bg-surface-2 text-left transition-colors"
              >
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
                      food.serving_size_g
                        ? `${Math.round(food.calories)} kcal / serving`
                        : `${Math.round(food.calories)} kcal / 100g`
                    )}
                  </p>
                </div>
                <ChevronRight size={14} className="text-muted shrink-0" />
              </button>
            );
          })}
        </div>
      )}

      {/* ── Entry screen ── */}
      {selected && (
        <div className="flex flex-col gap-4">

          {/* Back + food name */}
          <div className="flex items-start gap-2">
            <button
              onClick={() => { setSelected(null); setShowPicker(false); }}
              className="mt-0.5 p-1.5 rounded-lg hover:bg-surface-2 text-muted transition-colors shrink-0"
            >
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
                <button key={n} onClick={() => handleMealChange(n)}
                  className={`py-2 rounded-xl text-sm font-bold transition-colors
                    ${n === mealNumber
                      ? "bg-accent-blue text-white shadow-sm"
                      : "bg-surface-2 text-muted hover:bg-surface-3"}`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* ── Amount + Serving Size ── */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">
              Amount
            </label>

            {/* Amount + unit row */}
            <div className="flex gap-2 items-stretch">
              {/* Amount number */}
              <input
                ref={amountRef}
                type="number"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                className="input font-mono w-28 shrink-0"
                placeholder={servingOpt?.id === "g" ? "100" : "1"}
                min="0.1"
                step={servingOpt?.id === "g" ? "5" : "0.5"}
              />

              {/* Serving unit selector */}
              <button
                onClick={() => setShowPicker(p => !p)}
                className="flex-1 flex items-center justify-between gap-1 px-3 py-2.5 rounded-xl border border-surface-3 bg-surface-1 text-sm font-medium text-foreground hover:bg-surface-2 transition-colors min-w-0"
              >
                <span className="truncate text-left">
                  {servingOpt?.id === "g"
                    ? "g"
                    : servingOpt
                      ? `${servingOpt.label}${servingOpt.gramsEach ? ` — ${servingOpt.gramsEach % 1 === 0 ? servingOpt.gramsEach : servingOpt.gramsEach.toFixed(1)}g` : ""}`
                      : "—"}
                </span>
                <ChevronDown
                  size={14}
                  className={`text-muted shrink-0 transition-transform ${showPicker ? "rotate-180" : ""}`}
                />
              </button>
            </div>

            {/* Dropdown options */}
            {showPicker && servingOpts.length > 0 && (
              <div className="mt-1 rounded-xl border border-surface-3 bg-white shadow-lg overflow-hidden">
                {servingOpts.map((opt, i) => (
                  <button
                    key={opt.id}
                    onClick={() => {
                      // Keep the amount proportional when switching units
                      if (servingOpt && servingOpt.id !== opt.id) {
                        const currentGrams = amountNum * servingOpt.gramsEach;
                        const newAmount = opt.id === "g"
                          ? Math.round(currentGrams * 10) / 10
                          : Math.round((currentGrams / opt.gramsEach) * 100) / 100;
                        setAmount(String(newAmount));
                      }
                      setServingOpt(opt);
                      setShowPicker(false);
                    }}
                    className={`w-full flex items-center justify-between px-4 py-3 text-sm text-left transition-colors
                      ${i > 0 ? "border-t border-surface-2" : ""}
                      ${servingOpt?.id === opt.id
                        ? "bg-blue-50 text-accent-blue font-semibold"
                        : "hover:bg-surface-1 text-foreground"}`}
                  >
                    <span>{opt.id === "g" ? "g" : opt.label}</span>
                    {opt.id !== "g" && (
                      <span className="text-xs text-muted ml-2 shrink-0">
                        {opt.gramsEach % 1 === 0 ? opt.gramsEach : opt.gramsEach.toFixed(1)}g each
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {/* Context line: shows computed grams when using a named serving */}
            {servingOpt?.id !== "g" && amountNum > 0 && (
              <p className="text-[11px] text-muted mt-1.5">
                = {Math.round(qtyNum * 10) / 10}g logged
              </p>
            )}
          </div>

          {/* ── Set item weight — shown when no serving_size_g stored ── */}
          {selected && !selected.serving_size_g && !selected.recipe_id && (
            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 flex flex-col gap-3">
              <p className="text-xs font-semibold text-amber-800">Set item weight</p>
              <p className="text-[11px] text-amber-700 -mt-1">
                No weight stored for this food. Enter the gram weight of one item so quantity scales correctly.
              </p>

              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={itemWeightG}
                  onChange={e => setItemWeightG(e.target.value)}
                  placeholder="e.g. 22"
                  min="0.1"
                  step="0.5"
                  className="input font-mono w-24 shrink-0 text-sm"
                />
                <span className="text-sm text-amber-800 font-medium">g per item</span>
              </div>

              {/* Nutrition per item — only when all macros are zero */}
              {allMacrosZero && (
                <div className="flex flex-col gap-2">
                  <p className="text-[11px] text-amber-700 font-semibold">Nutrition per item (optional)</p>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: "Calories",  val: customCal,  set: setCustomCal,  unit: "kcal", color: "#FF9500" },
                      { label: "Protein",   val: customPro,  set: setCustomPro,  unit: "g",    color: "#34C759" },
                      { label: "Carbs",     val: customCarb, set: setCustomCarb, unit: "g",    color: "#007AFF" },
                      { label: "Fat",       val: customFat,  set: setCustomFat,  unit: "g",    color: "#FF3B30" },
                    ].map(({ label, val, set, unit, color }) => (
                      <div key={label}>
                        <label className="text-[10px] font-semibold mb-0.5 block" style={{ color }}>{label}</label>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            value={val}
                            onChange={e => set(e.target.value)}
                            placeholder="0"
                            min="0"
                            step="0.1"
                            className="input font-mono text-sm flex-1"
                          />
                          <span className="text-[11px] text-muted">{unit}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Save to food checkbox — only for foods already in DB */}
              {selected.id && (
                <label className="flex items-center gap-2 cursor-pointer select-none mt-0.5">
                  <input
                    type="checkbox"
                    checked={saveToFood}
                    onChange={e => setSaveToFood(e.target.checked)}
                    className="w-4 h-4 accent-amber-600 rounded"
                  />
                  <span className="text-[12px] text-amber-800">Save to this food for next time</span>
                </label>
              )}
            </div>
          )}

          {/* Time */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Time</label>
            <input
              type="time"
              value={time}
              onChange={e => { setTime(e.target.value); setTimeEdited(true); }}
              className="input font-mono"
            />
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
              {amountNum > 0
                ? servingOpt?.id === "g"
                  ? `${qtyNum}g`
                  : `${amountNum} × ${servingOpt?.gramsEach % 1 === 0 ? servingOpt?.gramsEach : servingOpt?.gramsEach.toFixed(1)}g = ${Math.round(qtyNum * 10) / 10}g`
                : "—"}
            </p>
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <button
            onClick={handleLog}
            disabled={logging || qtyNum <= 0}
            className="btn-primary flex items-center justify-center gap-2 w-full py-3.5 disabled:opacity-40"
          >
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
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div className="fixed bottom-0 left-0 right-0 w-full max-w-md mx-auto box-border z-50 overflow-hidden rounded-t-3xl shadow-2xl">
        <div
          className="bg-white w-full min-w-0 box-border flex flex-col gap-4 overflow-y-auto px-4 pt-5"
          style={{
            maxHeight: "85dvh",
            paddingBottom: "calc(90px + env(safe-area-inset-bottom, 0px))",
          }}
        >
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
