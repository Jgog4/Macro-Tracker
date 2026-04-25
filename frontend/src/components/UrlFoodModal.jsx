/**
 * UrlFoodModal — add a food to My Foods by either:
 *   (a) pasting a recipe URL  — AI fetches the page and estimates nutrition
 *   (b) pasting ingredient text — AI estimates nutrition directly from the text
 *
 * Many popular recipe sites (AllRecipes, etc.) block automated URL fetching.
 * In that case the user can switch to the Paste tab and paste the ingredient list.
 */
import { useState } from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, Link, ClipboardList, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { visionApi } from "../api/client";

const TABS = [
  { id: "url",  label: "URL",             Icon: Link          },
  { id: "text", label: "Paste Ingredients", Icon: ClipboardList },
];

export default function UrlFoodModal({ onClose, onSaved }) {
  const [tab,    setTab]    = useState("url");
  const [url,    setUrl]    = useState("");
  const [text,   setText]   = useState("");
  const [name,   setName]   = useState("");
  const [phase,  setPhase]  = useState("input");   // input | loading | done | error
  const [result, setResult] = useState(null);
  const [error,  setError]  = useState("");

  const canSubmit = tab === "url" ? url.trim().length > 0 : text.trim().length > 0;

  const handleAnalyze = async () => {
    if (!canSubmit) return;
    setPhase("loading");
    setError("");
    try {
      const res = tab === "url"
        ? await visionApi.fromUrl(url.trim(), name.trim() || null)
        : await visionApi.fromText(text.trim(), name.trim() || null);
      setResult(res.data);
      setPhase("done");
    } catch (e) {
      const msg = e.response?.data?.detail || "Analysis failed — please try again.";
      setError(msg);
      setPhase("error");
    }
  };

  const reset = () => {
    setPhase("input");
    setResult(null);
    setError("");
    setUrl("");
    setText("");
    setName("");
  };

  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "white" }}>

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-3 shrink-0" style={{ backgroundColor: "white" }}>
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 transition-colors text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <h1 className="text-base font-bold text-foreground">Add from Recipe</h1>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">

        {/* ── Tab toggle ── */}
        {(phase === "input" || phase === "error") && (
          <div className="flex bg-surface-2 rounded-xl p-1 gap-1">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => { setTab(t.id); setPhase("input"); setError(""); }}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-colors
                  ${tab === t.id ? "bg-white text-foreground shadow-sm" : "text-muted hover:text-foreground"}`}
              >
                <t.Icon size={12} />
                {t.label}
              </button>
            ))}
          </div>
        )}

        {/* ── Input phase ── */}
        {(phase === "input" || phase === "error") && (
          <>
            {tab === "url" ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted uppercase tracking-wide">Recipe URL</label>
                <input
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://www.example.com/recipe/..."
                  className="input w-full text-sm"
                  autoFocus
                  onKeyDown={e => e.key === "Enter" && handleAnalyze()}
                />
                <p className="text-[11px] text-muted mt-1">
                  Works with most recipe sites. If the site blocks the request,
                  switch to the <strong>Paste Ingredients</strong> tab instead.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted uppercase tracking-wide">Ingredient List</label>
                <textarea
                  value={text}
                  onChange={e => setText(e.target.value)}
                  placeholder={
                    "Paste the ingredient list here, e.g.:\n\n" +
                    "• 2 cups all-purpose flour\n" +
                    "• 1 cup sugar\n" +
                    "• 3 large eggs\n" +
                    "• 1/2 cup butter\n" +
                    "• Makes 12 servings"
                  }
                  className="input w-full text-sm font-normal resize-none"
                  rows={9}
                  autoFocus
                />
                <p className="text-[11px] text-muted mt-1">
                  Include the number of servings if you know it — Claude will estimate per-serving nutrition.
                </p>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                Food Name <span className="font-normal normal-case text-muted/60">(optional)</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Bee Sting Cake"
                className="input w-full text-sm"
              />
            </div>

            {phase === "error" && (
              <div className="flex items-start gap-3 bg-red-50 rounded-xl px-4 py-3">
                <AlertCircle size={16} className="text-accent-red shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm text-accent-red">{error}</p>
                  {tab === "url" && error.toLowerCase().includes("block") && (
                    <button
                      onClick={() => { setTab("text"); setPhase("input"); setError(""); }}
                      className="mt-2 text-xs font-semibold text-accent-blue underline"
                    >
                      Switch to Paste Ingredients →
                    </button>
                  )}
                </div>
              </div>
            )}

            <button
              onClick={handleAnalyze}
              disabled={!canSubmit}
              className="btn-primary py-3 text-sm font-semibold rounded-xl disabled:opacity-40"
            >
              {tab === "url" ? "Analyze Recipe" : "Estimate Nutrition"}
            </button>
          </>
        )}

        {/* ── Loading ── */}
        {phase === "loading" && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Loader2 size={32} className="animate-spin text-accent-blue" />
            <div className="text-center">
              <p className="font-semibold text-foreground">
                {tab === "url" ? "Analyzing recipe…" : "Estimating nutrition…"}
              </p>
              <p className="text-sm text-muted mt-1">
                {tab === "url" ? "Fetching page and estimating nutrition" : "Claude is calculating per-serving values"}
              </p>
            </div>
          </div>
        )}

        {/* ── Done ── */}
        {phase === "done" && result && (
          <>
            <div className="flex items-center gap-3 bg-green-50 rounded-xl px-4 py-3">
              <CheckCircle2 size={16} className="text-accent-green shrink-0" />
              <div>
                <p className="text-sm font-semibold text-foreground">{result.name}</p>
                <p className="text-[11px] text-muted">
                  Saved to My Foods
                  {result.serving_size_g != null ? ` · ${result.serving_size_g}g per serving` : ""}
                </p>
              </div>
            </div>

            {/* Macro cards */}
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: "Calories", value: result.calories,  unit: "kcal", color: "#FF9500", dec: 0 },
                { label: "Protein",  value: result.protein_g, unit: "g",    color: "#34C759", dec: 1 },
                { label: "Carbs",    value: result.carbs_g,   unit: "g",    color: "#007AFF", dec: 1 },
                { label: "Fat",      value: result.fat_g,     unit: "g",    color: "#FF3B30", dec: 1 },
              ].map(m => (
                <div key={m.label} className="bg-surface-1 rounded-xl py-3 flex flex-col items-center shadow-card">
                  <span className="text-sm font-bold font-mono" style={{ color: m.color }}>
                    {m.value != null ? m.value.toFixed(m.dec) : "—"}
                  </span>
                  <span className="text-[10px] text-muted mt-0.5">{m.label}</span>
                </div>
              ))}
            </div>

            {/* Key micros */}
            <div className="card-no-pad divide-y divide-surface-3">
              {[
                { label: "Fiber",        value: result.fiber_g,        unit: "g"   },
                { label: "Sugar",        value: result.sugar_g,        unit: "g"   },
                { label: "Sodium",       value: result.sodium_mg,      unit: "mg"  },
                { label: "Cholesterol",  value: result.cholesterol_mg, unit: "mg"  },
                { label: "Calcium",      value: result.calcium_mg,     unit: "mg"  },
                { label: "Iron",         value: result.iron_mg,        unit: "mg"  },
                { label: "Vitamin C",    value: result.vitamin_c_mg,   unit: "mg"  },
                { label: "Vitamin D",    value: result.vitamin_d_mcg,  unit: "mcg" },
              ].filter(r => r.value != null).map(r => (
                <div key={r.label} className="flex items-center justify-between px-4 py-2">
                  <span className="text-sm text-foreground">{r.label}</span>
                  <span className="text-sm font-mono text-muted">
                    {r.value < 10 ? r.value.toFixed(2) : r.value < 100 ? r.value.toFixed(1) : r.value.toFixed(0)} {r.unit}
                  </span>
                </div>
              ))}
            </div>

            <p className="text-[11px] text-muted text-center px-4">
              AI estimates based on the ingredient list. Actual values may vary.
            </p>

            <div className="flex gap-2">
              <button onClick={reset} className="flex-1 py-3 rounded-xl border border-surface-3 text-sm font-semibold text-muted">
                Add Another
              </button>
              <button onClick={onSaved} className="flex-1 btn-primary py-3 text-sm font-semibold rounded-xl">
                Done
              </button>
            </div>
          </>
        )}

        <div className="h-4" />
      </div>
    </div>,
    document.body
  );
}
