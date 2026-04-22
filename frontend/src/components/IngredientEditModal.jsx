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
  const [name,        setName]        = useState(ingredient.name        || "");
  const [calories,    setCalories]    = useState(String(ingredient.calories    ?? ""));
  const [protein,     setProtein]     = useState(String(ingredient.protein_g   ?? ""));
  const [carbs,       setCarbs]       = useState(String(ingredient.carbs_g     ?? ""));
  const [fat,         setFat]         = useState(String(ingredient.fat_g       ?? ""));
  const [servingG,    setServingG]    = useState(String(ingredient.serving_size_g ?? ""));
  const [fiber,       setFiber]       = useState(String(ingredient.fiber_g     ?? ""));
  const [sugar,       setSugar]       = useState(String(ingredient.sugar_g     ?? ""));
  const [sodium,      setSodium]      = useState(String(ingredient.sodium_mg   ?? ""));

  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState("");

  const num = v => { const n = parseFloat(v); return isNaN(n) ? null : n; };

  const handleSave = async () => {
    if (!name.trim()) { setError("Name is required"); return; }
    setSaving(true);
    setError("");
    try {
      await foodsApi.update(ingredient.id, {
        name:           name.trim(),
        calories:       num(calories),
        protein_g:      num(protein),
        carbs_g:        num(carbs),
        fat_g:          num(fat),
        serving_size_g: num(servingG),
        fiber_g:        num(fiber),
        sugar_g:        num(sugar),
        sodium_mg:      num(sodium),
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

        {/* Serving size */}
        <Field label="Serving size" unit="g" value={servingG} onChange={setServingG} placeholder="100" />

        {/* Core macros */}
        <div>
          <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
            Macros <span className="normal-case font-normal">per serving</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Calories" unit="kcal" value={calories} onChange={setCalories} />
            <Field label="Protein"  unit="g"    value={protein}  onChange={setProtein}  />
            <Field label="Carbs"    unit="g"    value={carbs}    onChange={setCarbs}    />
            <Field label="Fat"      unit="g"    value={fat}      onChange={setFat}      />
          </div>
        </div>

        {/* Extra nutrients */}
        <div>
          <p className="text-xs font-semibold text-muted uppercase tracking-wide mb-2">Other nutrients</p>
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
