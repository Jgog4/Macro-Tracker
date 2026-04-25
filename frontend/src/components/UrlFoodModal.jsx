/**
 * UrlFoodModal — paste a recipe URL and have the AI estimate
 * per-serving nutrition, then save to My Foods.
 */
import { useState } from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, Link, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { visionApi } from "../api/client";

export default function UrlFoodModal({ onClose, onSaved }) {
  const [url,    setUrl]    = useState("");
  const [name,   setName]   = useState("");
  const [phase,  setPhase]  = useState("input");   // "input" | "loading" | "done" | "error"
  const [result, setResult] = useState(null);
  const [error,  setError]  = useState("");

  const handleAnalyze = async () => {
    if (!url.trim()) return;
    setPhase("loading");
    setError("");
    try {
      const res = await visionApi.fromUrl(url.trim(), name.trim() || null);
      setResult(res.data);
      setPhase("done");
    } catch (e) {
      setError(
        e.response?.data?.detail ||
        "Could not analyze this URL. The site may block automated requests — try pasting the ingredient list as a screenshot instead."
      );
      setPhase("error");
    }
  };

  return createPortal(
    <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "white" }}>

      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b border-surface-3 shrink-0"
        style={{ backgroundColor: "white" }}
      >
        <button
          onClick={onClose}
          className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-surface-2 transition-colors text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-2">
          <Link size={15} className="text-accent-blue" />
          <h1 className="text-base font-bold text-foreground">Add from Link</h1>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-5 flex flex-col gap-5">

        {/* ── Input phase ── */}
        {(phase === "input" || phase === "error") && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                Recipe or Menu URL
              </label>
              <input
                type="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://www.example.com/recipes/chicken-stir-fry"
                className="input w-full text-sm"
                autoFocus
                onKeyDown={e => e.key === "Enter" && handleAnalyze()}
              />
              <p className="text-[11px] text-muted mt-1">
                Works best with recipe sites like AllRecipes, Food Network, NYT Cooking, etc.
              </p>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                Food Name <span className="font-normal normal-case text-muted/60">(optional — AI will infer if blank)</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. Chicken Stir Fry"
                className="input w-full text-sm"
              />
            </div>

            {phase === "error" && (
              <div className="flex items-start gap-3 bg-red-50 rounded-xl px-4 py-3">
                <AlertCircle size={16} className="text-accent-red shrink-0 mt-0.5" />
                <p className="text-sm text-accent-red">{error}</p>
              </div>
            )}

            <button
              onClick={handleAnalyze}
              disabled={!url.trim()}
              className="btn-primary py-3 text-sm font-semibold rounded-xl disabled:opacity-40"
            >
              Analyze Recipe
            </button>
          </>
        )}

        {/* ── Loading phase ── */}
        {phase === "loading" && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Loader2 size={32} className="animate-spin text-accent-blue" />
            <div className="text-center">
              <p className="font-semibold text-foreground">Analyzing recipe…</p>
              <p className="text-sm text-muted mt-1">Fetching page and estimating nutrition</p>
            </div>
          </div>
        )}

        {/* ── Done phase ── */}
        {phase === "done" && result && (
          <>
            <div className="flex items-center gap-3 bg-green-50 rounded-xl px-4 py-3">
              <CheckCircle2 size={16} className="text-accent-green shrink-0" />
              <div>
                <p className="text-sm font-semibold text-foreground">{result.name}</p>
                <p className="text-[11px] text-muted">
                  Saved to My Foods · {result.serving_size_desc || result.serving_size_g ? `${result.serving_size_g ?? "?"}g per serving` : "per serving"}
                </p>
              </div>
            </div>

            {/* Macro summary */}
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: "Calories", value: result.calories,   unit: "kcal", color: "#FF9500", dec: 0 },
                { label: "Protein",  value: result.protein_g,  unit: "g",    color: "#34C759", dec: 1 },
                { label: "Carbs",    value: result.carbs_g,    unit: "g",    color: "#007AFF", dec: 1 },
                { label: "Fat",      value: result.fat_g,       unit: "g",    color: "#FF3B30", dec: 1 },
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
            {(result.fiber_g || result.sodium_mg || result.cholesterol_mg) && (
              <div className="card-no-pad divide-y divide-surface-3">
                {result.fiber_g      != null && <NRow label="Fiber"       v={result.fiber_g}       u="g"  />}
                {result.sugar_g      != null && <NRow label="Sugar"       v={result.sugar_g}       u="g"  />}
                {result.sodium_mg    != null && <NRow label="Sodium"      v={result.sodium_mg}     u="mg" />}
                {result.cholesterol_mg != null && <NRow label="Cholesterol" v={result.cholesterol_mg} u="mg" />}
                {result.calcium_mg   != null && <NRow label="Calcium"     v={result.calcium_mg}    u="mg" />}
                {result.iron_mg      != null && <NRow label="Iron"        v={result.iron_mg}       u="mg" />}
                {result.vitamin_c_mg != null && <NRow label="Vitamin C"   v={result.vitamin_c_mg}  u="mg" />}
                {result.vitamin_d_mcg != null && <NRow label="Vitamin D"  v={result.vitamin_d_mcg} u="mcg"/>}
              </div>
            )}

            <p className="text-[11px] text-muted text-center px-4">
              These are AI estimates based on the recipe ingredients. Actual values may vary.
            </p>

            <div className="flex gap-2">
              <button
                onClick={() => { setPhase("input"); setResult(null); setUrl(""); setName(""); }}
                className="flex-1 py-3 rounded-xl border border-surface-3 text-sm font-semibold text-muted"
              >
                Add Another
              </button>
              <button
                onClick={onSaved}
                className="flex-1 btn-primary py-3 text-sm font-semibold rounded-xl"
              >
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}

function NRow({ label, v, u }) {
  return (
    <div className="flex items-center justify-between px-4 py-2">
      <span className="text-sm text-foreground">{label}</span>
      <span className="text-sm font-mono text-muted">
        {v < 10 ? v.toFixed(2) : v < 100 ? v.toFixed(1) : v.toFixed(0)} {u}
      </span>
    </div>
  );
}
