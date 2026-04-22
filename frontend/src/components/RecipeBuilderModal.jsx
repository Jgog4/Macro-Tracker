/**
 * Recipe Builder Modal — create or edit a recipe.
 *
 * Step 1 — Name + ingredient basket (search, set qty, see running totals)
 * Step 2 — Set cooked weight (serving_size_g)
 * Step 3 — Nutrition summary + Save
 */
import { useState, useEffect, useRef } from "react";
import { foodsApi, recipesApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import {
  Search, Loader2, Plus, Trash2, ChevronRight,
  ChevronLeft, Check, X, Scale,
} from "lucide-react";

const SOURCE_BADGE = {
  personal:   { label: "My Foods",   color: "bg-green-100 text-green-700" },
  restaurant: { label: "Restaurant", color: "bg-orange-100 text-orange-700" },
  usda:       { label: "USDA",       color: "bg-blue-100 text-blue-700" },
  custom:     { label: "Custom",     color: "bg-purple-100 text-purple-700" },
  usda_live:  { label: "USDA",       color: "bg-blue-100 text-blue-700" },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function calcTotals(basket) {
  return basket.reduce((acc, { food, qty }) => {
    const qtyNum = parseFloat(qty) || 0;
    const baseG  = food.serving_size_g || (qtyNum || 100);
    const ratio  = baseG > 0 ? qtyNum / baseG : 0;
    acc.calories += (food.calories  || 0) * ratio;
    acc.protein  += (food.protein_g || 0) * ratio;
    acc.carbs    += (food.carbs_g   || 0) * ratio;
    acc.fat      += (food.fat_g     || 0) * ratio;
    acc.totalG   += qtyNum;
    return acc;
  }, { calories: 0, protein: 0, carbs: 0, fat: 0, totalG: 0 });
}

// ── Main component ────────────────────────────────────────────────────────────

export default function RecipeBuilderModal({ recipe, onClose, onSaved }) {
  const isEdit = !!recipe;

  // Step: "ingredients" | "weight" | "summary"
  const [step, setStep] = useState("ingredients");

  // Recipe name
  const [name, setName] = useState(recipe?.name || "");

  // Basket: [{key, food, qty}]
  const [basket, setBasket] = useState(() => {
    if (!recipe) return [];
    return recipe.ingredients.map((ri, i) => ({
      key: i,
      food: {
        id:             ri.ingredient.id,
        name:           ri.ingredient.name,
        brand:          ri.ingredient.brand,
        calories:       ri.ingredient.calories,
        protein_g:      ri.ingredient.protein_g,
        fat_g:          ri.ingredient.fat_g,
        carbs_g:        ri.ingredient.carbs_g,
        serving_size_g: ri.ingredient.serving_size_g,
        source:         ri.ingredient.source,
      },
      qty: String(ri.quantity_g),
    }));
  });
  const basketCounter = useRef(recipe ? recipe.ingredients.length : 0);

  // Cooked weight
  const [cookedWeight, setCookedWeight] = useState(
    recipe?.serving_size_g ? String(recipe.serving_size_g) : ""
  );

  // Search
  const [query, setQuery]         = useState("");
  const [results, setResults]     = useState([]);
  const [searching, setSearching] = useState(false);
  const searchGen = useRef(0);
  const inputRef  = useRef();

  // Save
  const [saving, setSaving]   = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => { inputRef.current?.focus(); }, []);

  // ── Search effect ───────────────────────────────────────────────────────────
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

        const localFdcIds = new Set(localItems.map(i => i.usda_fdc_id).filter(Boolean));
        setResults([...localItems, ...usdaItems.filter(i => !localFdcIds.has(i.fdc_id))]);
      } catch { if (gen === searchGen.current) setResults([]); }
      finally  { if (gen === searchGen.current) setSearching(false); }
    }, 350);

    return () => clearTimeout(timer);
  }, [query]);

  // ── Basket ops ──────────────────────────────────────────────────────────────
  const addToBasket = (food) => {
    const defaultQty = food.serving_size_g ? String(food.serving_size_g) : "100";
    setBasket(b => [...b, { key: ++basketCounter.current, food, qty: defaultQty }]);
    setQuery("");
    setResults([]);
    inputRef.current?.focus();
  };

  const updateQty = (key, qty) => setBasket(b => b.map(i => i.key === key ? { ...i, qty } : i));
  const remove    = (key)      => setBasket(b => b.filter(i => i.key !== key));

  // ── Derived ─────────────────────────────────────────────────────────────────
  const totals      = calcTotals(basket);
  const weightNum   = parseFloat(cookedWeight) || totals.totalG;

  // Macros scaled to serving_size_g (cooked weight)
  const perServing = weightNum > 0 ? {
    calories: totals.calories,
    protein:  totals.protein,
    carbs:    totals.carbs,
    fat:      totals.fat,
  } : null;

  const per100 = weightNum > 0 ? {
    calories: totals.calories / weightNum * 100,
    protein:  totals.protein  / weightNum * 100,
    carbs:    totals.carbs    / weightNum * 100,
    fat:      totals.fat      / weightNum * 100,
  } : null;

  // ── Save ─────────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!name.trim() || basket.length === 0) return;
    setSaving(true);
    setSaveError("");
    try {
      // Import any live USDA items first
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

      const payload = {
        name:           name.trim(),
        serving_size_g: cookedWeight ? parseFloat(cookedWeight) : undefined,
        ingredients,
      };

      if (isEdit) {
        await recipesApi.update(recipe.id, payload);
      } else {
        await recipesApi.create(payload);
      }
      onSaved();
    } catch (e) {
      setSaveError(e.response?.data?.detail || "Failed to save recipe");
    } finally {
      setSaving(false);
    }
  };

  const canProceed = name.trim().length > 0 && basket.length > 0;

  // ── Render ───────────────────────────────────────────────────────────────────
  const title = isEdit ? `Edit: ${recipe.name}` : "New Recipe";

  return (
    <ModalShell onClose={onClose} title={title}>

      {/* ══════════════════════════════════════════════
          STEP 1 — Ingredients
          ══════════════════════════════════════════════ */}
      {step === "ingredients" && (
        <div className="flex flex-col gap-4">

          {/* Recipe name */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">
              Recipe Name
            </label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Turkey & Rice Bowl"
              className="input"
            />
          </div>

          {/* Search */}
          <div className="relative w-full min-w-0 box-border">
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
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-foreground">
                <X size={13} />
              </button>
            )}
          </div>

          {/* Search results */}
          {query.length >= 2 && (
            <div className="max-h-44 overflow-y-auto flex flex-col -mt-2 w-full min-w-0 box-border">
              {searching ? (
                <div className="flex justify-center py-5">
                  <Loader2 size={18} className="animate-spin text-muted" />
                </div>
              ) : results.length === 0 ? (
                <p className="text-center text-muted text-xs py-4">No results</p>
              ) : results.map((food, i) => {
                const badge = SOURCE_BADGE[food.source] || SOURCE_BADGE.custom;
                return (
                  <button key={food.id || food.fdc_id || i}
                    onClick={() => addToBasket(food)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-surface-2 text-left transition-colors w-full">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <p className="text-sm text-foreground">{food.name}</p>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0 ${badge.color}`}>
                          {badge.label}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted mt-0.5">
                        {food.brand ? `${food.brand} · ` : ""}
                        {food.calories != null && `${food.serving_size_g ? Math.round(food.calories / food.serving_size_g * 100) : Math.round(food.calories)} cal/100g`}
                      </p>
                    </div>
                    <Plus size={14} className="text-muted shrink-0" />
                  </button>
                );
              })}
            </div>
          )}

          {/* Basket */}
          {basket.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="text-[10px] text-muted uppercase tracking-wider px-1 font-semibold">
                Ingredients ({basket.length})
              </p>
              <div className="flex flex-col">
                {basket.map(({ key, food, qty }) => {
                  const qtyNum = parseFloat(qty) || 0;
                  const baseG  = food.serving_size_g || (qtyNum || 100);
                  const ratio  = baseG > 0 ? qtyNum / baseG : 0;
                  const kcal   = ((food.calories || 0) * ratio).toFixed(0);
                  return (
                    <div key={key}
                      className="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-surface-2 group">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-foreground truncate">{food.name}</p>
                        {food.brand && <p className="text-[10px] text-muted truncate">{food.brand}</p>}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <input
                          type="number"
                          value={qty}
                          onChange={e => updateQty(key, e.target.value)}
                          className="input w-16 font-mono py-1 px-2 text-right"
                          min="0.5" step="0.5"
                        />
                        <span className="text-[11px] text-muted">g</span>
                        <span className="text-[11px] font-mono text-muted w-14 text-right">{kcal} kcal</span>
                        <button onClick={() => remove(key)}
                          className="p-1 rounded-lg hover:bg-red-50 text-muted hover:text-accent-red">
                          <Trash2 size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Running totals */}
              <div className="bg-surface-2 rounded-xl p-3 mt-1">
                <div className="grid grid-cols-4 gap-2 mb-1">
                  {[
                    { label: "Calories", val: totals.calories, unit: "kcal", color: "#FF9500" },
                    { label: "Protein",  val: totals.protein,  unit: "g",    color: "#34C759" },
                    { label: "Carbs",    val: totals.carbs,    unit: "g",    color: "#007AFF" },
                    { label: "Fat",      val: totals.fat,      unit: "g",    color: "#FF3B30" },
                  ].map(({ label, val, unit, color }) => (
                    <div key={label} className="flex flex-col items-center">
                      <span className="text-sm font-bold font-mono" style={{ color }}>
                        {val >= 10 ? Math.round(val) : val.toFixed(1)}
                      </span>
                      <span className="text-[10px] text-muted">{unit}</span>
                      <span className="text-[9px] text-muted">{label}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-muted text-center">
                  Total raw weight: {Math.round(totals.totalG)}g
                </p>
              </div>
            </div>
          )}

          {basket.length === 0 && query.length < 2 && (
            <p className="text-center text-muted text-sm py-2">
              Search for ingredients above to start building your recipe
            </p>
          )}

          <button
            onClick={() => setStep("weight")}
            disabled={!canProceed}
            className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40">
            Next — Set Cooked Weight
            <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* ══════════════════════════════════════════════
          STEP 2 — Cooked weight
          ══════════════════════════════════════════════ */}
      {step === "weight" && (
        <div className="flex flex-col gap-5">
          <button onClick={() => setStep("ingredients")}
            className="flex items-center gap-1.5 text-accent-blue text-sm font-medium -mb-1">
            <ChevronLeft size={16} /> Back to ingredients
          </button>

          <div className="flex flex-col items-center gap-3 py-4">
            <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center">
              <Scale size={24} className="text-accent-blue" />
            </div>
            <div className="text-center">
              <p className="font-semibold text-foreground">What's the final cooked weight?</p>
              <p className="text-sm text-muted mt-1">
                Weigh the finished dish. Macros will be calculated per gram of cooked food.
              </p>
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">
              Cooked / Final Weight
            </label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                value={cookedWeight}
                onChange={e => setCookedWeight(e.target.value)}
                placeholder={String(Math.round(totals.totalG))}
                className="input flex-1 font-mono text-lg"
                min="1" step="1"
                autoFocus
              />
              <span className="text-muted font-medium">g</span>
            </div>
            <p className="text-[11px] text-muted mt-1.5">
              Total raw weight: {Math.round(totals.totalG)}g
              {cookedWeight && parseFloat(cookedWeight) > 0 && ` · ${((totals.totalG / parseFloat(cookedWeight) - 1) * 100).toFixed(0)}% water loss`}
            </p>
          </div>

          {/* Preview per 100g */}
          {per100 && (
            <div className="bg-surface-2 rounded-xl p-4">
              <p className="text-[10px] text-muted font-semibold uppercase tracking-wide mb-3">
                Macros per 100g cooked
              </p>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: "Calories", val: per100.calories, unit: "kcal", color: "#FF9500" },
                  { label: "Protein",  val: per100.protein,  unit: "g",    color: "#34C759" },
                  { label: "Carbs",    val: per100.carbs,    unit: "g",    color: "#007AFF" },
                  { label: "Fat",      val: per100.fat,      unit: "g",    color: "#FF3B30" },
                ].map(({ label, val, unit, color }) => (
                  <div key={label} className="flex flex-col items-center">
                    <span className="text-sm font-bold font-mono" style={{ color }}>
                      {val >= 10 ? Math.round(val) : val.toFixed(1)}
                    </span>
                    <span className="text-[10px] text-muted">{unit}</span>
                    <span className="text-[9px] text-muted">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={() => setStep("summary")}
              className="btn-ghost flex items-center gap-1.5 text-sm">
              Skip
            </button>
            <button
              onClick={() => setStep("summary")}
              className="btn-primary flex-1 flex items-center justify-center gap-2 py-3">
              Preview &amp; Save
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════
          STEP 3 — Summary + Save
          ══════════════════════════════════════════════ */}
      {step === "summary" && (
        <div className="flex flex-col gap-4">
          <button onClick={() => setStep("weight")}
            className="flex items-center gap-1.5 text-accent-blue text-sm font-medium -mb-1">
            <ChevronLeft size={16} /> Back
          </button>

          {/* Recipe title */}
          <div className="card flex flex-col gap-1">
            <p className="text-xs text-muted font-semibold uppercase tracking-wide">Recipe</p>
            <p className="text-lg font-bold text-foreground">{name}</p>
            <p className="text-sm text-muted">
              {basket.length} ingredient{basket.length !== 1 ? "s" : ""}
              {cookedWeight ? ` · ${cookedWeight}g cooked` : ` · ${Math.round(totals.totalG)}g raw`}
            </p>
          </div>

          {/* Macro summary */}
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Calories", val: perServing?.calories, unit: "kcal", color: "#FF9500" },
              { label: "Protein",  val: perServing?.protein,  unit: "g",    color: "#34C759" },
              { label: "Carbs",    val: perServing?.carbs,    unit: "g",    color: "#007AFF" },
              { label: "Fat",      val: perServing?.fat,      unit: "g",    color: "#FF3B30" },
            ].map(({ label, val, unit, color }) => (
              <div key={label} className="card flex flex-col gap-1">
                <p className="text-[10px] text-muted font-semibold uppercase tracking-wide">{label}</p>
                <p className="text-xl font-bold font-mono" style={{ color }}>
                  {val != null ? (val >= 10 ? Math.round(val) : val.toFixed(1)) : "—"}
                  <span className="text-xs text-muted font-normal ml-1">{unit}</span>
                </p>
                {per100 && (
                  <p className="text-[10px] text-muted">
                    {(label === "Calories" ? per100.calories : label === "Protein" ? per100.protein : label === "Carbs" ? per100.carbs : per100.fat) >= 10
                      ? Math.round(label === "Calories" ? per100.calories : label === "Protein" ? per100.protein : label === "Carbs" ? per100.carbs : per100.fat)
                      : (label === "Calories" ? per100.calories : label === "Protein" ? per100.protein : label === "Carbs" ? per100.carbs : per100.fat).toFixed(1)
                    } {unit}/100g
                  </p>
                )}
              </div>
            ))}
          </div>

          {/* Ingredient list */}
          <div className="card-no-pad">
            {basket.map(({ key, food, qty }, i) => (
              <div key={key}
                className={`flex items-center justify-between px-4 py-2.5
                  ${i !== basket.length - 1 ? "border-b border-surface-3" : ""}`}>
                <p className="text-sm text-foreground truncate flex-1 min-w-0">{food.name}</p>
                <span className="text-xs font-mono text-muted ml-2 shrink-0">{qty}g</span>
              </div>
            ))}
          </div>

          {saveError && <p className="text-accent-red text-xs">{saveError}</p>}

          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40">
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            {isEdit ? "Save Changes" : "Save Recipe"}
          </button>
        </div>
      )}
    </ModalShell>
  );
}
