/**
 * Vision / OCR modal — photo upload → GPT-4o-mini extracts macros → review → save.
 */
import { useState, useRef } from "react";
import { visionApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { Camera, Upload, Loader2, Check } from "lucide-react";

export default function VisionModal({ onClose, onSaved }) {
  const [step, setStep]         = useState("upload");   // upload | reviewing | saved
  const [preview, setPreview]   = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [name, setName]         = useState("");
  const fileRef = useRef();

  const handleFile = async (file) => {
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setLoading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await visionApi.extract(fd);
      setExtracted(res.data);
      setName(res.data.name || "");
      setStep("reviewing");
    } catch (e) {
      setError(e.response?.data?.detail || "Extraction failed");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", fileRef.current.files[0]);
      if (name) fd.append("name", name);
      await visionApi.extractAndSave(fd);
      setStep("saved");
      setTimeout(onSaved, 1200);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Scan Nutrition Label">
      {step === "upload" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            Take or upload a photo of a nutrition label or restaurant menu item.
            GPT-4o-mini will extract Calories, Protein, Fat, Carbs, Sodium & Cholesterol.
          </p>

          {/* Drop zone */}
          <label className="flex flex-col items-center justify-center gap-3 py-12 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-accent-blue transition-colors">
            <Camera size={28} className="text-muted" />
            <div className="text-center">
              <p className="text-sm font-medium">Tap to choose photo</p>
              <p className="text-xs text-muted mt-0.5">JPEG, PNG, or WebP</p>
            </div>
            <input
              ref={fileRef}
              type="file" accept="image/*" capture="environment"
              className="hidden"
              onChange={e => handleFile(e.target.files[0])}
            />
          </label>

          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted">
              <Loader2 size={16} className="animate-spin" /> Extracting macros…
            </div>
          )}
          {error && <p className="text-red-400 text-sm">{error}</p>}
        </div>
      )}

      {step === "reviewing" && extracted && (
        <div className="flex flex-col gap-4">
          {preview && (
            <img src={preview} alt="Label" className="w-full max-h-48 object-contain rounded-lg border border-border" />
          )}

          <div>
            <label className="text-xs text-subtle mb-1 block">Food Name</label>
            <input value={name} onChange={e => setName(e.target.value)} className="input" />
          </div>

          <div className="card-sm grid grid-cols-3 gap-y-3">
            {[
              { label: "Calories",    value: extracted.calories,    unit: "kcal" },
              { label: "Protein",     value: extracted.protein_g,   unit: "g" },
              { label: "Fat",         value: extracted.fat_g,       unit: "g" },
              { label: "Carbs",       value: extracted.carbs_g,     unit: "g" },
              { label: "Sodium",      value: extracted.sodium_mg,   unit: "mg" },
              { label: "Cholesterol", value: extracted.cholesterol_mg, unit: "mg" },
            ].map(({ label, value, unit }) => (
              <div key={label} className="flex flex-col">
                <span className="text-[10px] text-muted">{label}</span>
                <span className="text-sm font-mono font-semibold text-white">
                  {value != null ? `${value}${unit}` : "–"}
                </span>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted">
            <span className="text-accent-green">●</span>
            Confidence: {(extracted.confidence * 100).toFixed(0)}%
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <div className="flex gap-2">
            <button onClick={() => setStep("upload")} className="btn-ghost flex-1">Retake</button>
            <button onClick={handleSave} disabled={loading} className="btn-primary flex-1 flex items-center justify-center gap-2">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Save to DB
            </button>
          </div>
        </div>
      )}

      {step === "saved" && (
        <div className="flex flex-col items-center gap-3 py-8">
          <div className="w-12 h-12 rounded-full bg-accent-green/20 flex items-center justify-center">
            <Check size={24} className="text-accent-green" />
          </div>
          <p className="font-medium">Saved to your food database</p>
          <p className="text-sm text-muted">You can now log it from Add Food → Local</p>
        </div>
      )}
    </ModalShell>
  );
}
