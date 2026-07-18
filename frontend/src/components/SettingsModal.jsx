/**
 * SettingsModal — edit daily macro targets as % of total calories.
 * User sets total kcal + protein/carbs/fat % (must sum to 100). Grams derived
 * via 4/4/9 kcal per gram, so macros always match the calorie target.
 */
import { useState, useEffect } from "react";
import { format } from "date-fns";
import { Loader2, Check } from "lucide-react";
import { mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const KCAL_PER_G = { protein: 4, carbs: 4, fat: 9 };
const DEFAULTS = { calories: 2000, pctProtein: 30, pctCarbs: 40, pctFat: 30, sodium_mg: 2300, cholesterol_mg: 300 };

const MACROS = [
  { key: "protein", label: "Protein", color: "#34C759" },
  { key: "carbs",   label: "Carbs",   color: "#30B0C7" },
  { key: "fat",     label: "Fat",     color: "#AF52DE" },
];

export default function SettingsModal({ onClose, onSaved }) {
  const [calories, setCalories] = useState(DEFAULTS.calories);
  const [pct,      setPct]      = useState({ protein: DEFAULTS.pctProtein, carbs: DEFAULTS.pctCarbs, fat: DEFAULTS.pctFat });
  const [sodium,   setSodium]   = useState(DEFAULTS.sodium_mg);
  const [chol,     setChol]     = useState(DEFAULTS.cholesterol_mg);
  const [loading,  setLoading]  = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [error,    setError]    = useState("");

  useEffect(() => {
    mealsApi.getLatestTarget()
      .then(res => {
        const d = res.data;
        const cal = d.calories || DEFAULTS.calories;
        setCalories(cal);
        setSodium(d.sodium_mg ?? DEFAULTS.sodium_mg);
        setChol(d.cholesterol_mg ?? DEFAULTS.cholesterol_mg);
        // Derive % from stored grams
        if (cal > 0) {
          const p = Math.round((d.protein_g || 0) * 4 / cal * 100);
          const c = Math.round((d.carbs_g   || 0) * 4 / cal * 100);
          const f = Math.round((d.fat_g     || 0) * 9 / cal * 100);
          if (p + c + f > 0) setPct({ protein: p, carbs: c, fat: f });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const num = (v, fb) => { const n = parseFloat(v); return isNaN(n) ? fb : n; };
  const cal = num(calories, 0);
  const pctSum = num(pct.protein, 0) + num(pct.carbs, 0) + num(pct.fat, 0);
  const sumOk  = Math.abs(pctSum - 100) < 0.5;

  const grams = (key) => {
    const kcal = cal * num(pct[key], 0) / 100;
    return kcal / KCAL_PER_G[key];
  };

  const setP = (key) => (v) => setPct(prev => ({ ...prev, [key]: v }));

  const handleSave = async () => {
    if (!sumOk) { setError(`Percentages must add up to 100% (currently ${Math.round(pctSum)}%)`); return; }
    setSaving(true); setError("");
    try {
      await mealsApi.setTarget({
        target_date:    format(new Date(), "yyyy-MM-dd"),
        calories:       cal,
        protein_g:      Math.round(grams("protein") * 10) / 10,
        carbs_g:        Math.round(grams("carbs")   * 10) / 10,
        fat_g:          Math.round(grams("fat")     * 10) / 10,
        sodium_mg:      num(sodium, DEFAULTS.sodium_mg),
        cholesterol_mg: num(chol, DEFAULTS.cholesterol_mg),
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
            Macros are set as a % of calories, so they always add up to your energy target. Applies from today forward.
          </p>

          {/* Energy */}
          <div className="flex flex-col gap-1">
            <label className="text-xs font-semibold text-muted uppercase tracking-wide flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#FF9500" }} /> Energy (kcal)
            </label>
            <input type="number" min="0" step="10" inputMode="decimal" value={calories}
              onChange={e => setCalories(e.target.value)} className="input font-mono" />
          </div>

          {/* Macro % rows */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-muted uppercase tracking-wide">Macro split</span>
              <span className={`text-xs font-semibold font-mono ${sumOk ? "text-accent-green" : "text-accent-red"}`}>
                {Math.round(pctSum)}% {sumOk ? "✓" : "/ 100%"}
              </span>
            </div>
            {MACROS.map(({ key, label, color }) => (
              <div key={key} className="flex items-center gap-3">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                <span className="text-sm text-foreground w-16 shrink-0">{label}</span>
                <div className="flex items-center gap-1">
                  <input type="number" min="0" max="100" step="1" inputMode="decimal" value={pct[key]}
                    onChange={e => setP(key)(e.target.value)}
                    className="input font-mono w-16 text-center py-1.5" />
                  <span className="text-muted text-sm">%</span>
                </div>
                <span className="text-sm text-muted font-mono ml-auto">
                  {Math.round(grams(key))} g
                  <span className="text-[11px] text-muted/60"> · {Math.round(cal * num(pct[key], 0) / 100)} kcal</span>
                </span>
              </div>
            ))}
          </div>

          {!sumOk && (
            <p className="text-[11px] text-accent-red -mt-1">
              Percentages add up to {Math.round(pctSum)}% — adjust to total 100%.
            </p>
          )}

          {/* Absolute limits */}
          <div className="grid grid-cols-2 gap-3 pt-1 border-t border-surface-3">
            <div className="flex flex-col gap-1 pt-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">Sodium (mg)</label>
              <input type="number" min="0" step="50" value={sodium} onChange={e => setSodium(e.target.value)} className="input font-mono" />
            </div>
            <div className="flex flex-col gap-1 pt-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">Cholesterol (mg)</label>
              <input type="number" min="0" step="10" value={chol} onChange={e => setChol(e.target.value)} className="input font-mono" />
            </div>
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <button
            onClick={handleSave}
            disabled={saving || !sumOk}
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
