/**
 * Vision / OCR modal — photo upload(s) → Claude extracts macros → review → save.
 * Supports optional second photo (front of package / ingredients list).
 */
import { useState, useRef } from "react";
import { visionApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { Camera, Upload, Loader2, Check, Plus, X } from "lucide-react";

export default function VisionModal({ onClose, onSaved }) {
  const [step, setStep]           = useState("upload");   // upload | reviewing | saved
  const [preview1, setPreview1]   = useState(null);
  const [preview2, setPreview2]   = useState(null);
  const [file1, setFile1]         = useState(null);
  const [file2, setFile2]         = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [name, setName]           = useState("");
  const [servingSize, setServingSize] = useState("");
  const [servingSizeG, setServingSizeG] = useState("");

  const fileRef1 = useRef();
  const fileRef2 = useRef();

  const handleFile1 = (file) => {
    if (!file) return;
    setFile1(file);
    setPreview1(URL.createObjectURL(file));
    setError("");
  };

  const handleFile2 = (file) => {
    if (!file) return;
    setFile2(file);
    setPreview2(URL.createObjectURL(file));
    setError("");
  };

  const removeFile2 = () => {
    setFile2(null);
    setPreview2(null);
    if (fileRef2.current) fileRef2.current.value = "";
  };

  const handleExtract = async () => {
    if (!file1) return;
    setLoading(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file1);
      if (file2) fd.append("file2", file2);
      const res = await visionApi.extract(fd);
      setExtracted(res.data);
      setName(res.data.name || "");
      setServingSize(res.data.serving_size || "");
      setServingSizeG(res.data.serving_size_g != null ? String(res.data.serving_size_g) : "");
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
      fd.append("file", file1);
      if (file2) fd.append("file2", file2);
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

      {/* ── Upload step ── */}
      {step === "upload" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            Upload a photo of a nutrition facts label. Optionally add a second photo of the
            front of the package or ingredients list to help identify the product name.
          </p>

          {/* Photo 1 — required */}
          <div>
            <p className="text-xs text-subtle mb-1.5">Photo 1 — Nutrition label <span className="text-accent-red">*</span></p>
            {preview1 ? (
              <div className="relative">
                <img src={preview1} alt="Label" className="w-full max-h-44 object-contain rounded-xl border border-border" />
                <button
                  onClick={() => { setFile1(null); setPreview1(null); if (fileRef1.current) fileRef1.current.value = ""; }}
                  className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/70 flex items-center justify-center text-white hover:bg-red-500/80">
                  <X size={11} />
                </button>
              </div>
            ) : (
              <label className="flex flex-col items-center justify-center gap-3 py-8 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-accent-blue transition-colors">
                <Camera size={24} className="text-muted" />
                <p className="text-sm font-medium">Tap to add label photo</p>
                <input
                  ref={fileRef1}
                  type="file" accept="image/*" capture="environment"
                  className="hidden"
                  onChange={e => handleFile1(e.target.files[0])}
                />
              </label>
            )}
          </div>

          {/* Photo 2 — optional */}
          <div>
            <p className="text-xs text-subtle mb-1.5">Photo 2 — Package front / ingredients <span className="text-muted">(optional)</span></p>
            {preview2 ? (
              <div className="relative">
                <img src={preview2} alt="Package" className="w-full max-h-44 object-contain rounded-xl border border-border" />
                <button
                  onClick={removeFile2}
                  className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/70 flex items-center justify-center text-white hover:bg-red-500/80">
                  <X size={11} />
                </button>
              </div>
            ) : (
              <label className="flex flex-col items-center justify-center gap-2 py-5 border border-dashed border-border rounded-xl cursor-pointer hover:border-accent-blue transition-colors">
                <div className="flex items-center gap-2 text-muted">
                  <Plus size={14} />
                  <span className="text-xs">Add second photo</span>
                </div>
                <input
                  ref={fileRef2}
                  type="file" accept="image/*" capture="environment"
                  className="hidden"
                  onChange={e => handleFile2(e.target.files[0])}
                />
              </label>
            )}
          </div>

          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted">
              <Loader2 size={16} className="animate-spin" /> Extracting macros…
            </div>
          )}
          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            onClick={handleExtract}
            disabled={!file1 || loading}
            className="btn-primary flex items-center justify-center gap-2 py-3 disabled:opacity-40">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
            Extract Nutrition Info
          </button>
        </div>
      )}

      {/* ── Review step ── */}
      {step === "reviewing" && extracted && (
        <div className="flex flex-col gap-4">
          {/* Previews */}
          <div className={`grid gap-2 ${preview2 ? "grid-cols-2" : "grid-cols-1"}`}>
            {preview1 && (
              <img src={preview1} alt="Label" className="w-full max-h-36 object-contain rounded-lg border border-border" />
            )}
            {preview2 && (
              <img src={preview2} alt="Package" className="w-full max-h-36 object-contain rounded-lg border border-border" />
            )}
          </div>

          <div>
            <label className="text-xs text-subtle mb-1 block">Food Name</label>
            <input value={name} onChange={e => setName(e.target.value)} className="input" />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-subtle mb-1 block">Serving size (label)</label>
              <input value={servingSize} onChange={e => setServingSize(e.target.value)} className="input text-sm" placeholder="e.g. 1 cup (240mL)" />
            </div>
            <div>
              <label className="text-xs text-subtle mb-1 block">Serving size (g)</label>
              <input
                type="number"
                value={servingSizeG}
                onChange={e => setServingSizeG(e.target.value)}
                className="input text-sm font-mono"
                placeholder="100"
                min="0.1"
                step="0.5"
              />
            </div>
          </div>

          <div className="card-sm grid grid-cols-3 gap-y-3">
            {[
              { label: "Calories",    value: extracted.calories,       unit: "kcal" },
              { label: "Protein",     value: extracted.protein_g,      unit: "g" },
              { label: "Fat",         value: extracted.fat_g,          unit: "g" },
              { label: "Carbs",       value: extracted.carbs_g,        unit: "g" },
              { label: "Sodium",      value: extracted.sodium_mg,      unit: "mg" },
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

      {/* ── Saved step ── */}
      {step === "saved" && (
        <div className="flex flex-col items-center gap-3 py-8">
          <div className="w-12 h-12 rounded-full bg-accent-green/20 flex items-center justify-center">
            <Check size={24} className="text-accent-green" />
          </div>
          <p className="font-medium">Saved to your food database</p>
          <p className="text-sm text-muted">You can now log it from Add Food → Custom</p>
        </div>
      )}
    </ModalShell>
  );
}
