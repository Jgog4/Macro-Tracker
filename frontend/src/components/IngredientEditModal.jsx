/**
 * Edit a custom ingredient's name, macros, and serving size.
 * Used from the "My Foods" tab in LibraryPage.
 */
import { useState } from "react";
import { Loader2, Check } from "lucide-react";
import { foodsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

function Field({ label, value, onChange, unit, type = "number", placeholder = "0" }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-semibold text-muted uppercase tracking-wide">
        {label}{unit && <span className="normal-case font-normal ml-1">({unit})</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        min="0"
        step="0.1"
        className="input font-mono"
      />
    </div>
  );
}

export default function IngredientEditModal({ ingredient, onClose, onSaved }) {
  // Convert stored per-serving values to per-100g for display.
  // On save we convert back: store = display * (servingG / 100).
  const base = ingredient.serving_size_g || 100;
  const to100 = v => v != null ? String(Math.round((v / base) * 100 * 10) / 10) : "";

  const [name,        setName]        = useState(ingredient.name || "");
  const [calories,    setCalories]    = useState(to100(ingredient.calories));
  const [protein,     setProtein]     = useState(to100(ingredient.protein_g));
  const [carbs,       setCarbs]       = useState(to100(ingredient.carbs_g));
  const [fat,         setFat]         = useState(to100(ingredient.fat_g));
  const [fiber,       setFiber]       = useState(to100(ingredient.fiber_g));
  const [sugar,       setSugar]       = useState(to100(ingredient.sugar_g));
  const [sodium,      setSodium]      = useState(
    ingredient.sodium_mg != null ? String(Math.round((ingredient.sodium_mg / base) * 100 * 10) / 10) : ""
  );
  const [servingG,    setServingG]    = useState(String(ingredient.serving_size_g ?? ""));
  const [servingDesc, setServingDesc] = useState(ingredient.serving_size_desc || "");

  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState("");

  const num = v => { const n = parseFloat(v); return isNaN(n) ? null : n; };

  // Convert per-100g display values back to per-serving for storage
  const toServing = v => {
    const n = num(v);
    if (n == null) return null;
    const sg = num(servingG);
    return sg ? Math.round((n * sg / 100) * 1000) / 1000 : n; // if no serving set, store as-is (per 100g)
  };

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError("");
    try {
      await foodsApi.update(ingredient.id, {
        name:              name.trim(),
        calories:          toServing(calories),
        protein_g:         toServing(protein),
        carbs_g:           toServing(carbs),
        fat_g:             toServing(fat),
        fiber_g:           toServing(fiber),
        sugar_g:           toServing(sugar),
        sodium_mg:         toServing(sodium),
        serving_size_g:    num(servingG),
        serving_size_desc: servingDesc.trim() || null,
      });
      onSaved();
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Edit Food">
      <div className="flex flex-col gap-4">

        {/* Name */}
        <div className="flex flex-col gap-1">
          <label className="text-xs font-semibold text-muted uppercase tracking-wide">Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Food name"
            className="input"
            autoFocus
          />
        </div>

        {/* Unit size */}
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-xs font-semibold text-muted uppercase tracking-wide">Unit size <span className="normal-case font-normal">(optional)</span></p>
            <p className="text-[11px] text-muted mt-0.5">Set this to log by count — e.g. 1 cherry = 11g</p>
          </div>
          <div className="flex gap-3">
            <div className="flex flex-col gap-1 flex-1">
              <label className="text-[11px] text-muted">Unit name</label>
              <input
                type="text"
                value={servingDesc}
                onChange={e => setServingDesc(e.target.value)}
                placeholder="e.g. cherry, scoop, tablet, slice"
                className="input"
              />
            </div>
            <div className="flex flex-col gap-1 w-32">
              <label className="text-[11px] text-muted">Grams per unit</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  value={servingG}
                  onChange={e => setServingG(e.target.value)}
                  placeholder="11"
                  min="0" step="0.1"
                  className="input font-mono w-full"
                />
                <span className="text-muted text-sm shrink-0">g</span>
              </div>
            </div>
          </div>
          {servingG && parseFloat(servingG) > 0 && servingDesc.trim() && calories && (
            <p className="text-[11px] text-muted -mt-1">
              1 {servingDesc.trim()} = {servingG}g ={" "}
              <span className="font-semibold text-foreground">
                {Math.round(parseFloat(calories) * parseFloat(servingG) / 100)} kcal
              </span>
            </p>
          )}
        </div>

        {/* Core macros — always entered per 100g */}
        <div>
          <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
            Macros <span className="normal-case font-normal text-muted">per 100g</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Calories" unit="kcal" value={calories} onChange={setCalories} />
            <Field label="Protein"  unit="g"    value={protein}  onChange={setProtein}  />
            <Field label="Carbs"    unit="g"    value={carbs}    onChange={setCarbs}    />
            <Field label="Fat"      unit="g"    value={fat}      onChange={setFat}      />
          </div>
        </div>

        {/* Extra nutrients per 100g */}
        <div>
          <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
            Other nutrients <span className="normal-case font-normal">per 100g</span>
          </p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Fiber"  unit="g"  value={fiber}  onChange={setFiber}  />
            <Field label="Sugar"  unit="g"  value={sugar}  onChange={setSugar}  />
            <Field label="Sodium" unit="mg" value={sodium} onChange={setSodium} />
          </div>
        </div>

        {error && <p className="text-accent-red text-xs">{error}</p>}

        <button
          onClick={handleSave}
          disabled={saving || !name.trim()}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          Save Changes
        </button>
      </div>
    </ModalShell>
  );
}
