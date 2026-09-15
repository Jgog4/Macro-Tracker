/**
 * Import a recipe from a URL (or pasted ingredient text).
 *
 * Two screens: enter a URL → review the parse → save. The review screen is the
 * whole point of the feature. Confident lines collapse to one row; anything the
 * pipeline is unsure about expands with the reason stated in a plain sentence
 * and a one-tap fix, so a bad match is obvious before it reaches your diary.
 */
import { useEffect, useRef, useState } from "react";
import {
  Link2, Loader2, ClipboardPaste, AlertTriangle, Check, ChevronDown, ChevronRight,
  ExternalLink, Search,
} from "lucide-react";
import { foodsApi, recipeImportApi } from "../api/client";
import { ModalShell, selectAndReveal, decimalOnly } from "./AddFoodModal";

/** Plain-English explanation for each flag the parser can raise. */
const FLAG_TEXT = {
  optional:        "Marked optional in the recipe — excluded unless you switch it on.",
  garnish:         "A garnish — excluded unless you switch it on.",
  to_taste:        "“To taste” — counted as a token 1 g. Adjust if you used more.",
  partial_use:     "Only part of this is eaten (divided, reserved, or a discarded marinade). Check the amount.",
  sub_recipe:      "This refers to another recipe. Link one of yours or leave it out.",
  range:           "The recipe gave a range — the midpoint was used.",
  fat_drained:     "Fat is drained in the instructions, so some was subtracted.",
  calorie_outlier: "This line's calories look implausible — usually a unit or match error.",
};

const num = (v, d = 0) => (v == null ? "—" : Number(v).toFixed(d));

const NUTRIENT_KEYS = [
  "calories", "protein_g", "fat_g", "carbs_g", "sodium_mg",
  "cholesterol_mg", "fiber_g", "sugar_g", "sat_fat_g",
];

function foodToMatch(food) {
  const base = Number(food.serving_size_g) > 0 ? Number(food.serving_size_g) : 100;
  return {
    id: food.id,
    name: food.name,
    brand: food.brand || null,
    source: food.source,
    per_gram: Object.fromEntries(
      NUTRIENT_KEYS.map(key => [key, Number(food[key] || 0) / base])
    ),
  };
}

/** Search-and-select correction used for unmatched and incorrect lines. */
function FoodMatchSearch({ initialQuery, onChoose }) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState(initialQuery || "");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [choosing, setChoosing] = useState("");
  const [error, setError] = useState("");
  const generation = useRef(0);

  useEffect(() => {
    if (!expanded || query.trim().length < 2) {
      setResults([]);
      return undefined;
    }
    const current = ++generation.current;
    const timer = setTimeout(async () => {
      setSearching(true);
      setError("");
      const [local, usda] = await Promise.allSettled([
        foodsApi.search(query.trim(), { limit: 12 }),
        foodsApi.usdaSearch(query.trim(), 5),
      ]);
      if (current !== generation.current) return;
      const localRows = local.status === "fulfilled" ? local.value.data : [];
      const localFdc = new Set(localRows.map(row => row.usda_fdc_id).filter(Boolean));
      const liveRows = usda.status === "fulfilled"
        ? usda.value.data
            .filter(row => !localFdc.has(row.fdc_id))
            .map(row => ({
              id: null,
              fdc_id: row.fdc_id,
              name: row.description,
              brand: row.brand_owner,
              source: "usda_live",
              calories: row.calories,
              protein_g: row.protein_g,
              fat_g: row.fat_g,
              carbs_g: row.carbs_g,
              serving_size_g: 100,
            }))
        : [];
      setResults([...localRows, ...liveRows]);
      setSearching(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [expanded, query]);

  const choose = async (food) => {
    setChoosing(food.id || String(food.fdc_id));
    setError("");
    try {
      const selected = food.source === "usda_live"
        ? (await foodsApi.importUsda(food.fdc_id)).data
        : food;
      onChoose(foodToMatch(selected));
      setExpanded(false);
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't select that food.");
    } finally {
      setChoosing("");
    }
  };

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="text-[11px] text-accent-blue font-semibold self-start flex items-center gap-1"
      >
        <Search size={12} /> Find another food
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-surface-3 bg-surface-1 p-2 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <Search size={12} className="text-muted shrink-0" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search foods or USDA…"
          className="bg-transparent outline-none text-xs flex-1 min-w-0 py-1"
          autoFocus
        />
      </div>
      <div className="max-h-40 overflow-y-auto divide-y divide-surface-3">
        {searching ? (
          <div className="py-4 flex justify-center"><Loader2 size={15} className="animate-spin text-muted" /></div>
        ) : results.length ? results.map(food => {
          const key = food.id || `usda-${food.fdc_id}`;
          const kcal100 = food.serving_size_g
            ? Number(food.calories || 0) / Number(food.serving_size_g) * 100
            : Number(food.calories || 0);
          return (
            <button key={key} type="button" onClick={() => choose(food)}
              disabled={!!choosing}
              className="w-full text-left py-2 flex items-center gap-2 disabled:opacity-50">
              <span className="flex-1 min-w-0">
                <span className="block text-xs text-foreground truncate">{food.name}</span>
                <span className="block text-[10px] text-muted truncate">
                  {food.brand ? `${food.brand} · ` : ""}{Math.round(kcal100)} kcal/100g · {food.source === "usda_live" ? "USDA" : "My database"}
                </span>
              </span>
              {choosing === (food.id || String(food.fdc_id))
                ? <Loader2 size={12} className="animate-spin" />
                : <ChevronRight size={12} className="text-muted" />}
            </button>
          );
        }) : query.trim().length >= 2 ? (
          <p className="text-[10px] text-muted text-center py-3">No matching foods</p>
        ) : null}
      </div>
      {error && <p className="text-[10px] text-accent-red">{error}</p>}
      <button type="button" onClick={() => setExpanded(false)}
        className="text-[10px] text-muted self-end">Cancel</button>
    </div>
  );
}

/** How a line's gram weight was arrived at, in plain words. */
const WEIGHT_SOURCE = {
  mass:           null,                       // stated outright, nothing to say
  density:        "Converted from volume.",
  usda:           "From a USDA household measure.",
  count:          "Standard weight for one item.",
  count_default:  "No size given — assumed medium. Adjust if yours differ.",
  to_taste:       null,
  "item:user":    "Your saved weight for one of these.",
  "item:cache":   "Looked up once and remembered — check it the first time.",
  "item:curated": "Standard weight for one item. Adjust if yours differ.",
  "item:usda":    "Estimated from USDA item weights — worth a glance.",
};

export default function RecipeImportModal({ onClose, onSaved }) {
  const [step, setStep]       = useState("input");   // input | review
  const [url, setUrl]         = useState("");
  const [paste, setPaste]     = useState("");
  const [showPaste, setShowPaste] = useState(false);
  const [locale, setLocale]   = useState("us");
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState("");

  const [draft, setDraft]     = useState(null);
  const [lines, setLines]     = useState([]);
  const [servings, setServings] = useState(1);
  const [cookedWeight, setCookedWeight] = useState("");
  const [title, setTitle]     = useState("");
  const [open, setOpen]       = useState({});        // expanded rows
  const [saving, setSaving]   = useState(false);

  // ── run the pipeline ──────────────────────────────────────────────────────
  const runImport = async (useText) => {
    setBusy(true); setError("");
    try {
      const body = useText ? { text: paste, locale } : { url: url.trim(), locale };
      const { data } = await recipeImportApi.preview(body);
      setDraft(data);
      setLines(data.lines.map(l => ({
        ...l,
        alias_learn: false,
        weight_was_edited: false,
      })));
      setServings(data.num_servings || 1);
      setTitle(data.title || "Imported recipe");
      // Open the rows that need attention so nothing needing a decision hides.
      setOpen(Object.fromEntries(data.lines.map((l, i) => [i, !!l.needs_review])));
      setStep("review");
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(detail || "Couldn't import that recipe.");
      if (e.response?.status === 422) setShowPaste(true);   // fall into the paste box
    } finally { setBusy(false); }
  };

  // ── live totals, recomputed from the edited lines ─────────────────────────
  const totals = lines.reduce((acc, l) => {
    if (!l.include || !l.nutrition) return acc;
    acc.calories += l.nutrition.calories || 0;
    acc.protein  += l.nutrition.protein_g || 0;
    acc.fat      += l.nutrition.fat_g || 0;
    acc.carbs    += l.nutrition.carbs_g || 0;
    acc.grams    += l.grams || 0;
    return acc;
  }, { calories: 0, protein: 0, fat: 0, carbs: 0, grams: 0 });
  const perServing = totals.calories / Math.max(1, servings);

  const patchLine = (i, patch) =>
    setLines(ls => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  /** Re-price a line locally when its grams or matched food changes. */
  const reprice = (line, grams, match) => {
    const g = grams == null ? line.grams : grams;
    // Omitting the third parameter preserves the match. Passing null is an
    // intentional unmatched choice, which must clear its old nutrition rather
    // than silently retaining the prior food's macros.
    const m = match === undefined ? line.match : match;
    if (!m || !g || !m.per_gram) return { ...line, grams: g, match: m, nutrition: null };
    const n = Object.fromEntries(Object.entries(m.per_gram).map(([k, v]) => [k, v * g]));
    const retention = line.fat_retention ?? 1;
    if (retention < 1 && n.fat_g) {
      const removedFat = n.fat_g * (1 - retention);
      n.fat_g *= retention;
      n.calories = Math.max(0, (n.calories || 0) - removedFat * 9);
    }
    return { ...line, grams: g, match: m, nutrition: n };
  };

  const save = async () => {
    setSaving(true); setError("");
    try {
      const { data } = await recipeImportApi.save({
        title,
        source_url: draft.source_url,
        num_servings: Number(servings) || 1,
        cooked_weight_g: cookedWeight ? Number(cookedWeight) : null,
        import_id: draft.import_id,
        lines: lines.map(l => ({
          name: l.name, ingredient_id: l.match?.id || null,
          grams: l.grams, include: l.include, raw: l.raw, alias_learn: !!l.alias_learn,
          // Sent so a hand-typed weight for a counted item can be remembered.
          quantity: l.quantity, unit: l.unit,
          unit_is_mass: ["mass", "density", "usda"].includes(l.gram_method),
          weight_was_edited: !!l.weight_was_edited,
          fat_retention: l.fat_retention ?? 1,
        })),
      });
      onSaved?.(data);
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Couldn't save the recipe.");
    } finally { setSaving(false); }
  };

  // ── screen 1: URL / paste ─────────────────────────────────────────────────
  if (step === "input") {
    return (
      <ModalShell onClose={onClose} title="Import Recipe">
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted -mt-1">
            Paste a recipe link. Ingredients are matched against verified nutrition
            data — never guessed by AI.
          </p>

          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">
              Recipe URL
            </label>
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-2 bg-surface-2 rounded-xl px-3">
                <Link2 size={15} className="text-muted shrink-0" />
                <input
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://…"
                  inputMode="url" autoCapitalize="off" autoCorrect="off"
                  className="flex-1 bg-transparent py-3 text-sm outline-none text-foreground"
                />
              </div>
              <button
                onClick={() => runImport(false)}
                disabled={busy || !url.trim()}
                className="btn-primary px-4 flex items-center gap-1.5 disabled:opacity-40">
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                Import
              </button>
            </div>
          </div>

          <button
            onClick={() => setShowPaste(v => !v)}
            className="flex items-center gap-1.5 text-accent-blue text-sm font-medium self-start">
            <ClipboardPaste size={14} />
            {showPaste ? "Hide paste box" : "Or paste the ingredient list"}
          </button>

          {showPaste && (
            <div>
              <textarea
                value={paste}
                onChange={e => setPaste(e.target.value)}
                rows={7}
                placeholder={"2 cups cooked chicken\n1 tbsp olive oil\n400g can chopped tomatoes"}
                className="input w-full text-sm font-mono leading-relaxed"
              />
              <button
                onClick={() => runImport(true)}
                disabled={busy || paste.trim().split("\n").filter(Boolean).length < 2}
                className="btn-primary w-full mt-2 py-3 flex items-center justify-center gap-2 disabled:opacity-40">
                {busy && <Loader2 size={14} className="animate-spin" />}
                Import pasted ingredients
              </button>
            </div>
          )}

          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">
              Measuring units
            </label>
            <div className="grid grid-cols-4 gap-1">
              {[["us", "US"], ["metric", "Metric"], ["uk", "UK"], ["au", "AU"]].map(([v, label]) => (
                <button key={v} onClick={() => setLocale(v)}
                  className={`py-2 rounded-xl text-xs font-semibold transition-colors
                    ${locale === v ? "bg-accent-blue text-white" : "bg-surface-2 text-muted"}`}>
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-muted mt-1.5">
              A tablespoon is 15 ml in the UK but 20 ml in Australia — this keeps
              imported recipes honest.
            </p>
          </div>

          {error && (
            <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
              <p className="text-xs text-amber-800">{error}</p>
            </div>
          )}
        </div>
      </ModalShell>
    );
  }

  // ── screen 2: review ──────────────────────────────────────────────────────
  const reviewCount = lines.filter(l => l.needs_review).length;
  const unresolvedCount = lines.filter(l => l.include && (!l.match || !l.grams)).length;

  return (
    <ModalShell onClose={onClose} title="Review Import">
      <div className="flex flex-col gap-3">

        <input
          value={title}
          onChange={e => setTitle(e.target.value)}
          className="input font-semibold"
        />

        {draft?.source_url && (
          <a href={draft.source_url} target="_blank" rel="noreferrer"
             className="flex items-center gap-1.5 text-accent-blue text-xs -mt-1">
            <ExternalLink size={12} /> View the original recipe
          </a>
        )}

        {(draft?.warnings?.length > 0 || reviewCount > 0) && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5 flex flex-col gap-1">
            {reviewCount > 0 && (
              <p className="text-xs text-amber-900 font-medium">
                {reviewCount} line{reviewCount === 1 ? "" : "s"} need a quick look.
              </p>
            )}
            {draft?.warnings?.map((w, i) => (
              <p key={i} className="text-[11px] text-amber-800">{w}</p>
            ))}
          </div>
        )}

        {/* Ingredient rows */}
        <div className="flex flex-col divide-y divide-surface-3 rounded-xl bg-surface-1 overflow-hidden">
          {lines.map((l, i) => {
            const kcal = l.nutrition?.calories;
            const flagged = l.needs_review;
            return (
              <div key={i} className={l.include ? "" : "opacity-50"}>
                <button
                  onClick={() => setOpen(o => ({ ...o, [i]: !o[i] }))}
                  className="w-full flex items-center gap-2 px-3 py-2.5 text-left">
                  <span className="shrink-0">
                    {flagged
                      ? <AlertTriangle size={14} className="text-amber-500" />
                      : <Check size={14} className="text-accent-green" />}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm text-foreground truncate">{l.name}</span>
                    <span className="block text-[11px] text-muted truncate">
                      {l.grams ? `${num(l.grams)} g` : "weight needed"}
                      {l.match ? ` · ${l.match.name}` : " · no match"}
                    </span>
                  </span>
                  <span className="text-xs font-mono text-muted shrink-0">
                    {kcal ? `${num(kcal)} kcal` : "—"}
                  </span>
                  {open[i] ? <ChevronDown size={14} className="text-muted shrink-0" />
                           : <ChevronRight size={14} className="text-muted shrink-0" />}
                </button>

                {open[i] && (
                  <div className="px-3 pb-3 flex flex-col gap-2 bg-surface-2/40">
                    <p className="text-[11px] text-muted font-mono">{l.raw}</p>

                    {l.flags?.map(f => FLAG_TEXT[f] && (
                      <p key={f} className="text-[11px] text-amber-800 bg-amber-50 rounded-lg px-2 py-1.5">
                        {FLAG_TEXT[f]}
                      </p>
                    ))}
                    {WEIGHT_SOURCE[l.gram_method] && (
                      <p className="text-[11px] text-muted bg-surface-2 rounded-lg px-2 py-1.5">
                        {WEIGHT_SOURCE[l.gram_method]}
                      </p>
                    )}
                    {l.adjustment_note && (
                      <p className="text-[11px] text-accent-blue bg-blue-50 rounded-lg px-2 py-1.5">
                        {l.adjustment_note}
                      </p>
                    )}

                    {l.ingredient_options?.length > 1 && (
                      <div className="flex flex-col gap-1.5 rounded-lg bg-blue-50 px-2 py-2">
                        <p className="text-[10px] text-accent-blue font-semibold">
                          This is an either/or ingredient — choose one.
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {l.ingredient_options.map(option => {
                            const selected = option.name === l.name;
                            return (
                              <button
                                key={option.name}
                                type="button"
                                onClick={() => setLines(ls => ls.map((x, j) => {
                                  if (j !== i) return x;
                                  const updated = reprice(x, x.grams, option.match);
                                  return {
                                    ...updated,
                                    name: option.name,
                                    alternates: option.alternates || [],
                                    alias_learn: false,
                                    needs_review: !option.match || !x.grams,
                                  };
                                }))}
                                className={`text-[11px] px-2 py-1 rounded-md font-semibold ${
                                  selected
                                    ? "bg-accent-blue text-white"
                                    : "bg-white text-accent-blue border border-blue-200"
                                }`}
                              >
                                {selected ? `Using ${option.name}` : `Use ${option.name} instead`}
                              </button>
                            );
                          })}
                        </div>
                        <p className="text-[10px] text-muted">
                          Switching keeps the same recipe weight; it does not add both foods.
                        </p>
                      </div>
                    )}

                    <div className="flex items-center gap-2">
                      <label className="text-[11px] text-muted w-14">Weight</label>
                      <input
                        type="text" inputMode="decimal"
                        defaultValue={l.grams ?? ""}
                        onInput={e => {
                          // Read the value NOW. React invokes a state updater
                          // after the event finishes dispatching, and
                          // `currentTarget` is null by then — reading it inside
                          // the updater threw on every keystroke.
                          const grams = Number(decimalOnly(e.currentTarget.value)) || null;
                          setLines(ls => ls.map((x, j) => (j === i
                            ? { ...reprice(x, grams), weight_was_edited: true }
                            : x)));
                        }}
                        onFocus={selectAndReveal}
                        placeholder="grams"
                        className="input w-24 font-mono py-1 px-2 text-sm"
                      />
                      <span className="text-[11px] text-muted">g</span>
                      <button
                        onClick={() => patchLine(i, { include: !l.include })}
                        className={`ml-auto text-[11px] font-semibold px-2.5 py-1.5 rounded-lg
                          ${l.include ? "bg-surface-3 text-muted" : "bg-accent-blue text-white"}`}>
                        {l.include ? "Exclude" : "Include"}
                      </button>
                    </div>

                    {l.flags?.includes("fat_drained") && (
                      <div className="flex items-center gap-2">
                        <label className="text-[11px] text-muted w-24">Fat retained</label>
                        <input
                          type="text"
                          inputMode="decimal"
                          defaultValue={Math.round((l.fat_retention ?? 0.5) * 100)}
                          onInput={e => {
                            const percent = Math.max(
                              0,
                              Math.min(100, Number(decimalOnly(e.currentTarget.value)) || 0)
                            );
                            const fat_retention = percent / 100;
                            setLines(ls => ls.map((x, j) =>
                              j === i
                                ? reprice({ ...x, fat_retention }, null)
                                : x
                            ));
                          }}
                          onFocus={selectAndReveal}
                          className="input w-20 font-mono py-1 px-2 text-sm"
                        />
                        <span className="text-[11px] text-muted">%</span>
                      </div>
                    )}

                    {l.alternates?.length > 1 && (
                      <div className="flex flex-col gap-1">
                        <p className="text-[10px] text-muted uppercase tracking-wide">Matched to</p>
                        {l.alternates.map(a => (
                          <button
                            key={a.id}
                            onClick={() => setLines(ls => ls.map((x, j) =>
                              j === i ? { ...reprice(x, null, a), alias_learn: a.id !== x.match?.id } : x))}
                            className={`text-left text-[11px] px-2 py-1.5 rounded-lg flex items-center gap-2
                              ${a.id === l.match?.id ? "bg-blue-50 text-accent-blue font-semibold" : "hover:bg-surface-2 text-foreground"}`}>
                            <span className="flex-1 truncate">{a.name}</span>
                            <span className="text-[9px] text-muted uppercase shrink-0">{a.source}</span>
                          </button>
                        ))}
                        <p className="text-[10px] text-muted">
                          Changing the match teaches the importer for next time.
                        </p>
                      </div>
                    )}

                    <FoodMatchSearch
                      initialQuery={l.name}
                      onChoose={match => setLines(ls => ls.map((x, j) =>
                        j === i
                          ? {
                              ...reprice(x, null, match),
                              alternates: [match, ...(x.alternates || []).filter(a => a.id !== match.id)],
                              alias_learn: true,
                              needs_review: !x.grams,
                            }
                          : x
                      ))}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Servings + weighed portion */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[11px] font-semibold text-muted uppercase tracking-wide mb-1 block">
              Servings
            </label>
            <input
              type="text" inputMode="decimal" defaultValue={servings}
              onInput={e => setServings(Number(decimalOnly(e.currentTarget.value)) || 1)}
              onFocus={selectAndReveal}
              className="input w-full font-mono"
            />
          </div>
          <div>
            <label className="text-[11px] font-semibold text-muted uppercase tracking-wide mb-1 block">
              Cooked weight
            </label>
            <input
              type="text" inputMode="decimal" value={cookedWeight}
              onChange={e => setCookedWeight(decimalOnly(e.target.value))}
              onFocus={selectAndReveal}
              placeholder={num(totals.grams)}
              className="input w-full font-mono"
            />
          </div>
        </div>
        <p className="text-[10px] text-muted -mt-1">
          Weigh the finished dish and you can log it by grams later instead of
          guessing what a sixth of a casserole looks like.
        </p>

        {draft?.cooking_notes?.map((n, i) => (
          <p key={i} className="text-[10px] text-muted">{n}</p>
        ))}

        {/* Live totals */}
        <div className="bg-surface-2 rounded-2xl p-3">
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Calories", val: perServing, unit: "kcal", color: "#FF9500", d: 0 },
              { label: "Protein",  val: totals.protein / Math.max(1, servings), unit: "g", color: "#34C759", d: 1 },
              { label: "Carbs",    val: totals.carbs  / Math.max(1, servings), unit: "g", color: "#007AFF", d: 1 },
              { label: "Fat",      val: totals.fat    / Math.max(1, servings), unit: "g", color: "#FF3B30", d: 1 },
            ].map(({ label, val, unit, color, d }) => (
              <div key={label} className="flex flex-col items-center">
                <span className="text-base font-bold font-mono" style={{ color }}>{num(val, d)}</span>
                <span className="text-[10px] text-muted">{unit}</span>
                <span className="text-[9px] text-subtle">{label}</span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-muted mt-2 text-center">
            per serving · {num(totals.calories)} kcal total · {num(totals.grams)} g
          </p>
        </div>

        {error && <p className="text-accent-red text-xs">{error}</p>}

        {unresolvedCount > 0 && (
          <p className="text-[11px] text-amber-700">
            Match and weigh all {unresolvedCount} included ingredient{unresolvedCount === 1 ? "" : "s"}, or exclude them before saving.
          </p>
        )}

        <div className="flex gap-2">
          <button onClick={() => setStep("input")} className="btn-ghost px-4">Back</button>
          <button
            onClick={save}
            disabled={saving || unresolvedCount > 0 || !lines.some(l => l.include && l.match && l.grams)}
            className="btn-primary flex-1 flex items-center justify-center gap-2 py-3 disabled:opacity-40">
            {saving && <Loader2 size={14} className="animate-spin" />}
            Save Recipe
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
