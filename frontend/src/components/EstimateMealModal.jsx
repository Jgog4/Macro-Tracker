/**
 * Estimate Meal — photograph a restaurant/home meal, describe what's in it,
 * and get an AI-estimated macro + component breakdown you can adjust before saving.
 *
 * Flow:  input (photos + description) → estimate → review/adjust → save & log
 */
import { useState, useEffect, useRef } from "react";
import { Camera, ImagePlus, Loader2, Sparkles, Trash2, X, Check, ChevronLeft } from "lucide-react";
import { visionApi, foodsApi, mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const num = (v) => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

function rowsFromEstimate(estimate) {
  return (estimate.ingredients || []).map((it, i) => {
    const grams = num(it.quantity_g);
    return {
      key: i,
      name: it.name || "Item",
      grams,
      calories: it.calories ?? 0,
      protein_g: it.protein_g ?? 0,
      carbs_g: it.carbs_g ?? 0,
      fat_g: it.fat_g ?? 0,
      // Keep stable per-gram values so repeated edits do not compound rounding.
      perGram: grams > 0 ? {
        calories: num(it.calories) / grams,
        protein_g: num(it.protein_g) / grams,
        carbs_g: num(it.carbs_g) / grams,
        fat_g: num(it.fat_g) / grams,
      } : null,
    };
  });
}

/**
 * Downscale + re-encode an image to JPEG before upload.
 * Critical on mobile: iPhone photos are 2-5 MB and often HEIC, which the
 * vision API rejects. Canvas re-encoding fixes the format AND cuts the
 * payload ~20x so uploads survive a slow cellular connection.
 */
async function prepareImage(file, maxDim = 1400, quality = 0.82) {
  const dataUrl = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
  const img = await new Promise((res, rej) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => rej(new Error("Could not read that image"));
    i.src = dataUrl;
  });
  const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
  const w = Math.max(1, Math.round(img.width * scale));
  const h = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(img, 0, 0, w, h);
  const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));
  if (!blob) throw new Error("Could not process that image");
  return new File([blob], "meal.jpg", { type: "image/jpeg" });
}

export default function EstimateMealModal({ dateStr, defaultMealNumber, onClose, onLogged }) {
  const [step, setStep]               = useState("input");   // input | review
  const [photos, setPhotos]           = useState([]);        // {file, url}
  const [description, setDescription] = useState("");
  const [dishName, setDishName]       = useState("");
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");

  // Review state
  const [result, setResult]     = useState(null);   // original AI response (micros live here)
  const [rows, setRows]         = useState([]);     // editable component rows
  const [name, setName]         = useState("");
  const [mealNumber, setMealNumber] = useState(defaultMealNumber ?? 1);
  const [time, setTime]         = useState(nowTimeStr);
  const [mealTimes, setMealTimes] = useState({});
  const [timeEdited, setTimeEdited] = useState(false);
  const [adjustment, setAdjustment] = useState("");
  const [refining, setRefining] = useState(false);
  const [saveAsSingleEntry, setSaveAsSingleEntry] = useState(false);
  const [saving, setSaving]     = useState(false);

  const cameraRef = useRef();
  const libraryRef = useRef();

  // Use the established diary time when adding another item to an existing meal.
  useEffect(() => {
    if (!dateStr) return;
    mealsApi.getDay(dateStr).then((res) => {
      const times = {};
      (res.data?.meals || []).forEach((meal) => {
        if (!meal.logged_at) return;
        const d = new Date(meal.logged_at);
        times[meal.meal_number] = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
      });
      setMealTimes(times);
    }).catch(() => {});
  }, [dateStr]);

  useEffect(() => {
    if (timeEdited) return;
    setTime(mealTimes[mealNumber] || nowTimeStr());
  }, [mealNumber, mealTimes, timeEdited]);

  const handleMealChange = (number) => {
    setTimeEdited(false);
    setMealNumber(number);
  };

  // ── Photos ────────────────────────────────────────────────────────────────
  const addFiles = (fileList) => {
    const incoming = Array.from(fileList || []).slice(0, 4 - photos.length);
    setPhotos((p) => [...p, ...incoming.map((f) => ({ file: f, url: URL.createObjectURL(f) }))]);
  };
  const removePhoto = (i) => setPhotos((p) => p.filter((_, idx) => idx !== i));

  // ── Estimate ──────────────────────────────────────────────────────────────
  const handleEstimate = async () => {
    if (!photos.length && !description.trim()) {
      setError("Add a photo or describe the meal (or both).");
      return;
    }
    setLoading(true); setError("");
    try {
      const fd = new FormData();
      // Shrink + convert to JPEG so HEIC and multi-MB phone photos both work
      for (const p of photos) {
        try {
          fd.append("files", await prepareImage(p.file));
        } catch {
          setError("One of the photos couldn't be read. Try a different one.");
          setLoading(false);
          return;
        }
      }
      if (description.trim()) fd.append("description", description.trim());
      if (dishName.trim())    fd.append("name", dishName.trim());

      const res = await visionApi.estimateMeal(fd);
      const d = res.data;
      setResult(d);
      setName(d.name || dishName.trim() || "Meal");
      setRows(rowsFromEstimate(d));
      setStep("review");
    } catch (e) {
      // Distinguish real server errors from network/timeout so failures are debuggable
      if (e.code === "ECONNABORTED") {
        setError("Timed out. Try again, or use fewer/smaller photos on a slow connection.");
      } else if (!e.response) {
        setError("Network error — check your connection and try again.");
      } else {
        setError(e.response?.data?.detail || `Server error (${e.response.status}). Try again.`);
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Row editing: changing grams scales that row's macros ──────────────────
  const updateGrams = (key, newGrams) => {
    // A blank value is valid while the user replaces the existing number.
    if (newGrams === "") {
      setRows((rs) => rs.map((r) => r.key === key ? { ...r, grams: "" } : r));
      return;
    }
    if (!/^\d*(?:\.\d*)?$/.test(newGrams)) return;

    // Turn "05" into "5", while preserving decimals such as "0.5".
    const cleaned = newGrams.replace(/^0+(?=\d)/, "");
    const g = num(cleaned);
    setRows((rs) =>
      rs.map((r) => {
        if (r.key !== key) return r;
        if (!r.perGram) return { ...r, grams: cleaned };
        return {
          ...r,
          grams: cleaned,
          calories:  Math.round(r.perGram.calories  * g * 10) / 10,
          protein_g: Math.round(r.perGram.protein_g * g * 10) / 10,
          carbs_g:   Math.round(r.perGram.carbs_g   * g * 10) / 10,
          fat_g:     Math.round(r.perGram.fat_g     * g * 10) / 10,
        };
      })
    );
  };
  const finishGramsEdit = (key) => {
    setRows((rs) => rs.map((r) => {
      if (r.key !== key || r.grams !== "") return r;
      return { ...r, grams: 0, calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
    }));
  };
  const removeRow = (key) => setRows((rs) => rs.filter((r) => r.key !== key));

  // ── Totals from rows (fall back to AI totals if no breakdown) ─────────────
  const hasRows = rows.length > 0;
  const totals = hasRows
    ? rows.reduce(
        (a, r) => ({
          calories:  a.calories  + num(r.calories),
          protein_g: a.protein_g + num(r.protein_g),
          carbs_g:   a.carbs_g   + num(r.carbs_g),
          fat_g:     a.fat_g     + num(r.fat_g),
          grams:     a.grams     + num(r.grams),
        }),
        { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0, grams: 0 }
      )
    : {
        calories:  result?.calories  ?? 0,
        protein_g: result?.protein_g ?? 0,
        carbs_g:   result?.carbs_g   ?? 0,
        fat_g:     result?.fat_g     ?? 0,
        grams:     result?.serving_size_g ?? 0,
      };

  // Micros scale with how much the calories changed vs the original estimate
  const microScale =
    result?.calories && result.calories > 0 ? totals.calories / result.calories : 1;

  // Send the current editable breakdown back to AI, so a refinement honours
  // any gram changes the user has already made in this review screen.
  const currentEstimate = () => ({
    ...result,
    name: name.trim() || result?.name || "Meal",
    serving_size_g: totals.grams,
    calories: totals.calories,
    protein_g: totals.protein_g,
    carbs_g: totals.carbs_g,
    fat_g: totals.fat_g,
    ingredients: rows.map((r) => ({
      name: r.name,
      quantity_g: num(r.grams),
      calories: num(r.calories),
      protein_g: num(r.protein_g),
      carbs_g: num(r.carbs_g),
      fat_g: num(r.fat_g),
    })),
  });

  const handleRefine = async () => {
    if (!adjustment.trim() || !result) return;
    setRefining(true); setError("");
    try {
      const res = await visionApi.refineMealEstimate({
        estimate: currentEstimate(),
        instruction: adjustment.trim(),
      });
      const revised = res.data;
      setResult(revised);
      setName(revised.name || name);
      setRows(rowsFromEstimate(revised));
      setAdjustment("");
    } catch (e) {
      setError(e.response?.data?.detail || "Could not update the estimate. Please try again.");
    } finally {
      setRefining(false);
    }
  };

  // ── Save as adjustable components, or as one combined food + log it ──────
  const handleSave = async () => {
    if (!name.trim()) { setError("Give the meal a name"); return; }
    setSaving(true); setError("");
    try {
      const MICROS = [
        "fiber_g","sugar_g","sat_fat_g","trans_fat_g","cholesterol_mg","sodium_mg",
        "potassium_mg","calcium_mg","iron_mg","magnesium_mg","zinc_mg","phosphorus_mg",
        "vitamin_a_mcg","vitamin_c_mg","vitamin_d_mcg","vitamin_e_mg","vitamin_k_mcg",
        "thiamine_mg","riboflavin_mg","niacin_mg","folate_mcg","cobalamin_mcg",
        "monounsaturated_fat_g","polyunsaturated_fat_g",
        "omega3_ala_g","omega3_epa_g","omega3_dha_g","caffeine_mg","alcohol_g",
      ];
      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(`${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`);

      if (!saveAsSingleEntry && hasRows) {
        // Each AI component becomes its own internal food record. Its macros are
        // stored for the estimated component weight, making later diary weight
        // edits scale exactly like any other logged food without cluttering My Foods.
        const componentRows = rows.filter(row => num(row.grams) > 0);
        if (!componentRows.length) throw new Error("Keep at least one component to log separately.");

        const created = await Promise.all(componentRows.map(async (row) => {
          const grams = num(row.grams);
          const calorieShare = totals.calories > 0
            ? num(row.calories) / totals.calories
            : 1 / componentRows.length;
          const payload = {
            source: "estimated_component",
            name: row.name,
            serving_size_g: Math.round(grams * 10) / 10,
            serving_size_desc: `AI estimate · ${name.trim()}`,
            calories:  Math.round(num(row.calories) * 10) / 10,
            protein_g: Math.round(num(row.protein_g) * 10) / 10,
            carbs_g:   Math.round(num(row.carbs_g) * 10) / 10,
            fat_g:     Math.round(num(row.fat_g) * 10) / 10,
          };
          // AI gives micros for the full dish, not each component. Allocate them
          // by calorie share so the meal total is preserved and still scales on edit.
          MICROS.forEach((key) => {
            const value = result?.[key];
            if (value != null) payload[key] = Math.round(value * microScale * calorieShare * 1000) / 1000;
          });
          return foodsApi.create(payload);
        }));

        await mealsApi.logFood({
          log_date: dateStr,
          meal_number: mealNumber,
          logged_at: loggedAt.toISOString(),
          items: created.map((response, index) => ({
            ingredient_id: response.data.id,
            quantity_g: num(componentRows[index].grams),
          })),
        });
      } else {
        const payload = {
          source: "custom",
          name: name.trim(),
          serving_size_g: Math.round(totals.grams) || null,
          serving_size_desc: "1 meal",
          calories:  Math.round(totals.calories * 10) / 10,
          protein_g: Math.round(totals.protein_g * 10) / 10,
          carbs_g:   Math.round(totals.carbs_g * 10) / 10,
          fat_g:     Math.round(totals.fat_g * 10) / 10,
        };
        MICROS.forEach((key) => {
          const value = result?.[key];
          if (value != null) payload[key] = Math.round(value * microScale * 1000) / 1000;
        });

        const created = await foodsApi.create(payload);
        await mealsApi.logFood({
          log_date: dateStr,
          meal_number: mealNumber,
          logged_at: loggedAt.toISOString(),
          items: [{ ingredient_id: created.data.id, quantity_g: payload.serving_size_g || 100 }],
        });
      }

      onLogged?.();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  // ══════════════════════════════════════════════════════════════════════════
  return (
    <ModalShell onClose={onClose} title="Estimate Meal">
      {step === "input" && (
        <div className="flex flex-col gap-4">
          <p className="text-[11px] text-muted -mt-1">
            Snap the meal and say what's in it — you'll get an itemised estimate you can adjust.
          </p>

          {/* Photos */}
          <div className="flex flex-wrap gap-2">
            {photos.map((p, i) => (
              <div key={i} className="relative w-20 h-20 rounded-xl overflow-hidden bg-surface-2">
                <img src={p.url} alt="" className="w-full h-full object-cover" />
                <button
                  onClick={() => removePhoto(i)}
                  className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center"
                >
                  <X size={11} />
                </button>
              </div>
            ))}
            {photos.length < 4 && (
              <>
                <button
                  onClick={() => cameraRef.current?.click()}
                  className="w-20 h-20 rounded-xl border-2 border-dashed border-surface-3 flex flex-col items-center justify-center gap-1 text-muted"
                >
                  <Camera size={18} />
                  <span className="text-[10px]">Camera</span>
                </button>
                <button
                  onClick={() => libraryRef.current?.click()}
                  className="w-20 h-20 rounded-xl border-2 border-dashed border-surface-3 flex flex-col items-center justify-center gap-1 text-muted"
                >
                  <ImagePlus size={18} />
                  <span className="text-[10px]">Library</span>
                </button>
              </>
            )}
          </div>
          <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden
                 onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          <input ref={libraryRef} type="file" accept="image/*" multiple hidden
                 onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />

          {/* Description */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-muted uppercase tracking-wide">
              What's in it?
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              placeholder={"e.g. grilled salmon (~180g), roast potatoes, green salad with olive oil vinaigrette, glass of white wine"}
              className="input resize-none leading-snug"
            />
            <p className="text-[11px] text-muted">
              The more detail — portion sizes, oils, sauces — the better the estimate.
            </p>
          </div>

          {/* Optional name */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-muted uppercase tracking-wide">
              Dish name <span className="normal-case font-normal">(optional)</span>
            </label>
            <input value={dishName} onChange={(e) => setDishName(e.target.value)}
                   placeholder="e.g. Salmon dinner — Café Central" className="input" />
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <button
            onClick={handleEstimate}
            disabled={loading || (!photos.length && !description.trim())}
            className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {loading ? "Estimating…" : "Estimate Macros"}
          </button>
        </div>
      )}

      {step === "review" && (
        <div className="flex flex-col gap-4">
          <button onClick={() => setStep("input")}
                  className="flex items-center gap-1 text-accent-blue text-sm font-medium self-start -mb-1">
            <ChevronLeft size={16} /> Back
          </button>

          {/* Name */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-muted uppercase tracking-wide">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className="input" />
          </div>

          {/* Natural-language refinement */}
          <div className="rounded-xl border border-accent-purple/20 bg-purple-50/50 p-3 flex flex-col gap-2">
            <label className="text-xs font-semibold text-accent-purple uppercase tracking-wide">
              Adjust estimate with AI
            </label>
            <textarea
              value={adjustment}
              onChange={(e) => setAdjustment(e.target.value)}
              rows={2}
              placeholder="e.g. The beef was much leaner — reduce its fat by about 50%."
              className="input resize-none leading-snug bg-white"
            />
            <button
              onClick={handleRefine}
              disabled={refining || !adjustment.trim()}
              className="btn-outline self-start flex items-center gap-1.5 disabled:opacity-40"
            >
              {refining ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {refining ? "Updating…" : "Update estimate"}
            </button>
            <p className="text-[10px] text-muted">
              AI will revise the relevant components, macros, and micronutrients. You can adjust grams afterward or save directly.
            </p>
          </div>

          {/* Totals */}
          <div className="bg-surface-2 rounded-xl p-3">
            <div className="grid grid-cols-4 gap-2">
              {[
                { l: "Calories", v: totals.calories, u: "kcal", c: "#FF9500", d: 0 },
                { l: "Protein",  v: totals.protein_g, u: "g",   c: "#34C759", d: 1 },
                { l: "Carbs",    v: totals.carbs_g,   u: "g",   c: "#30B0C7", d: 1 },
                { l: "Fat",      v: totals.fat_g,     u: "g",   c: "#AF52DE", d: 1 },
              ].map(({ l, v, u, c, d }) => (
                <div key={l} className="flex flex-col items-center">
                  <span className="text-base font-bold font-mono" style={{ color: c }}>{v.toFixed(d)}</span>
                  <span className="text-[10px] text-muted">{u}</span>
                  <span className="text-[9px] text-muted">{l}</span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-muted text-center mt-2">
              {Math.round(totals.grams)}g total
              {result?.confidence != null && ` · ${Math.round(result.confidence * 100)}% confidence`}
            </p>
          </div>

          {result?.notes && (
            <p className="text-[11px] text-muted bg-amber-50 rounded-lg px-3 py-2">
              <span className="font-semibold">Assumptions: </span>{result.notes}
            </p>
          )}

          {/* Components */}
          {hasRows && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-semibold text-muted uppercase tracking-wide">
                Components — adjust grams or remove
              </p>
              <div className="flex flex-col divide-y divide-surface-3 card-no-pad">
                {rows.map((r) => (
                  <div key={r.key} className="flex items-center gap-2 px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground leading-snug">{r.name}</p>
                      <p className="text-[11px] text-muted">
                        {Math.round(r.calories)} kcal · {r.protein_g.toFixed(1)}P · {r.carbs_g.toFixed(1)}C · {r.fat_g.toFixed(1)}F
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <input
                        type="text" inputMode="decimal"
                        value={r.grams}
                        onChange={(e) => updateGrams(r.key, e.target.value)}
                        onFocus={(e) => e.target.select()}
                        onBlur={() => finishGramsEdit(r.key)}
                        className="input font-mono w-16 text-center py-1.5 px-1"
                      />
                      <span className="text-[11px] text-muted">g</span>
                    </div>
                    <button onClick={() => removeRow(r.key)}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-muted hover:text-accent-red shrink-0">
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Meal + time */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">Meal</label>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <button key={n} onClick={() => handleMealChange(n)}
                  className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors
                    ${mealNumber === n ? "bg-accent-blue text-white" : "bg-surface-2 text-muted"}`}>
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">Time</label>
            <input type="time" value={time} onChange={(e) => { setTime(e.target.value); setTimeEdited(true); }}
                   className="input font-mono text-center" />
          </div>

          {hasRows && (
            <button
              type="button"
              onClick={() => setSaveAsSingleEntry(value => !value)}
              className="flex items-center justify-between gap-3 rounded-xl bg-surface-2 px-3 py-3 text-left"
            >
              <div>
                <p className="text-sm font-semibold text-foreground">Save as one meal entry</p>
                <p className="text-[11px] text-muted mt-0.5">
                  {saveAsSingleEntry
                    ? "One combined entry saved to My Foods"
                    : "Default: log components separately so each weight stays editable"}
                </p>
              </div>
              <span className={`w-11 h-6 rounded-full relative shrink-0 transition-colors ${saveAsSingleEntry ? "bg-accent-blue" : "bg-surface-3"}`}>
                <span className={`absolute top-0.5 w-5 h-5 bg-surface-1 rounded-full shadow transition-transform ${saveAsSingleEntry ? "translate-x-5" : "translate-x-0.5"}`} />
              </span>
            </button>
          )}

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <div className="sticky bottom-0 bg-surface-1 pt-2 pb-1 -mx-4 px-4 border-t border-surface-3">
            <button onClick={handleSave} disabled={saving}
                    className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40">
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
              {saveAsSingleEntry || !hasRows ? "Save one meal entry & Log" : `Log ${rows.filter(row => num(row.grams) > 0).length} components`}
            </button>
            <p className="text-[10px] text-muted text-center mt-1.5 mb-1">
              AI estimate — always approximate. Adjust anything that looks off.
            </p>
          </div>
        </div>
      )}
    </ModalShell>
  );
}
