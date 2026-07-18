/**
 * SettingsModal — edit daily macro targets.
 * Loads the current target and upserts it (effective from today forward).
 */
import { useState, useEffect } from "react";
import { format } from "date-fns";
import { Loader2, Check } from "lucide-react";
import { mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const DEFAULTS = { calories: 2000, protein_g: 150, carbs_g: 250, fat_g: 70, sodium_mg: 2300, cholesterol_mg: 300 };

function Field({ label, value, onChange, unit, color }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-semibold text-muted uppercase tracking-wide flex items-center gap-1.5">
        {color && <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />}
        {label}<span className="normal-case font-normal">({unit})</span>
      </label>
      <input
        type="number" min="0" step="1" inputMode="decimal"
        value={value}
        onChange={e => onChange(e.target.value)}
        className="input font-mono"
      />
    </div>
  );
}

export default function SettingsModal({ onClose, onSaved }) {
  const [vals,    setVals]    = useState(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState("");

  useEffect(() => {
    mealsApi.getLatestTarget()
      .then(res => {
        const d = res.data;
        setVals({
          calories:       d.calories       ?? DEFAULTS.calories,
          protein_g:      d.protein_g      ?? DEFAULTS.protein_g,
          carbs_g:        d.carbs_g        ?? DEFAULTS.carbs_g,
          fat_g:          d.fat_g          ?? DEFAULTS.fat_g,
          sodium_mg:      d.sodium_mg      ?? DEFAULTS.sodium_mg,
          cholesterol_mg: d.cholesterol_mg ?? DEFAULTS.cholesterol_mg,
        });
      })
      .catch(() => {}) // no target yet → keep defaults
      .finally(() => setLoading(false));
  }, []);

  const set = (k) => (v) => setVals(prev => ({ ...prev, [k]: v }));
  const num = (v, fallback) => { const n = parseFloat(v); return isNaN(n) ? fallback : n; };

  // Calorie cross-check from macros (4/4/9)
  const kcalFromMacros = Math.round(
    num(vals.protein_g, 0) * 4 + num(vals.carbs_g, 0) * 4 + num(vals.fat_g, 0) * 9
  );
  const kcalSet = num(vals.calories, 0);
  const mismatch = kcalSet > 0 && Math.abs(kcalFromMacros - kcalSet) / kcalSet > 0.08;

  const handleSave = async () => {
    setSaving(true); setError("");
    try {
      await mealsApi.setTarget({
        target_date:    format(new Date(), "yyyy-MM-dd"),
        calories:       num(vals.calories, DEFAULTS.calories),
        protein_g:      num(vals.protein_g, DEFAULTS.protein_g),
        carbs_g:        num(vals.carbs_g, DEFAULTS.carbs_g),
        fat_g:          num(vals.fat_g, DEFAULTS.fat_g),
        sodium_mg:      num(vals.sodium_mg, DEFAULTS.sodium_mg),
        cholesterol_mg: num(vals.cholesterol_mg, DEFAULTS.cholesterol_mg),
      });
      onSaved?.();
      onClose();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to save targets");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Macro Targets">
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={20} className="animate-spin text-muted" /></div>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-[11px] text-muted -mt-1">
            Applies from today forward. Past days keep the targets that were set then.
          </p>

          <Field label="Energy" unit="kcal" value={vals.calories} onChange={set("calories")} color="#FF9500" />

          <div className="grid grid-cols-3 gap-3">
            <Field label="Protein"   unit="g" value={vals.protein_g} onChange={set("protein_g")} color="#34C759" />
            <Field label="Carbs"     unit="g" value={vals.carbs_g}   onChange={set("carbs_g")}   color="#30B0C7" />
            <Field label="Fat"       unit="g" value={vals.fat_g}     onChange={set("fat_g")}     color="#AF52DE" />
          </div>

          {/* Calorie cross-check */}
          <div className={`text-[11px] rounded-lg px-3 py-2 ${mismatch ? "bg-orange-50 text-accent-orange" : "bg-surface-2 text-muted"}`}>
            Macros add up to <span className="font-semibold font-mono">{kcalFromMacros} kcal</span>
            {mismatch && ` — doesn't match your ${Math.round(kcalSet)} kcal target`}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Sodium"      unit="mg" value={vals.sodium_mg}      onChange={set("sodium_mg")} />
            <Field label="Cholesterol" unit="mg" value={vals.cholesterol_mg} onChange={set("cholesterol_mg")} />
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Save Targets
          </button>
        </div>
      )}
    </ModalShell>
  );
}
