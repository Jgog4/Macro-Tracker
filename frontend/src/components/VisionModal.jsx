/**
 * Vision / OCR modal — upload photos → Claude extracts/estimates macros → review → save.
 *
 * mode="label"    → reads a nutrition label  (existing behaviour)
 * mode="estimate" → estimates from ingredient list / package screenshot (supports 1–5 photos)
 *
 * Changes vs. previous version:
 *  - Removed capture="environment" so iOS opens the photo library (not the camera directly)
 *  - Replaced fixed file1/file2 with a dynamic array (up to 5 photos) in estimate mode
 */
import { useState, useRef } from "react";
import { visionApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { Camera, Upload, Loader2, Check, Plus, X } from "lucide-react";

export default function VisionModal({ onClose, onSaved, mode = "label" }) {
  const [step, setStep]               = useState("upload");   // upload | reviewing | saved
  const [files, setFiles]             = useState([]);          // dynamic array in estimate mode
  const [previews, setPreviews]       = useState([]);          // parallel array of object URLs
  // label mode keeps a single slot
  const [file1, setFile1]             = useState(null);
  const [preview1, setPreview1]       = useState(null);
  const [extracted, setExtracted]     = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState("");
  const [name, setName]               = useState("");
  const [servingSize, setServingSize] = useState("");
  const [servingSizeG, setServingSizeG] = useState("");

  const addFileRef  = useRef();   // "add photo" hidden input
  const fileRef1    = useRef();   // label-mode hidden input

  // ── Estimate mode — add a photo ───────────────────────────────────────────
  const handleAddFile = (file) => {
    if (!file || files.length >= 5) return;
    setFiles(prev => [...prev, file]);
    setPreviews(prev => [...prev, URL.createObjectURL(file)]);
    setError("");
    // Reset the input so the same file can be re-selected if needed
    if (addFileRef.current) addFileRef.current.value = "";
  };

  const handleRemoveFile = (idx) => {
    URL.revokeObjectURL(previews[idx]);
    setFiles(prev => prev.filter((_, i) => i !== idx));
    setPreviews(prev => prev.filter((_, i) => i !== idx));
  };

  // ── Label mode — single photo ─────────────────────────────────────────────
  const handleFile1 = (file) => {
    if (!file) return;
    setFile1(file);
    setPreview1(URL.createObjectURL(file));
    setError("");
  };

  // ── Extract / Estimate ────────────────────────────────────────────────────
  const handleExtract = async () => {
    const hasImages = mode === "estimate" ? files.length > 0 : !!file1;
    if (!hasImages) return;
    setLoading(true);
    setError("");
    try {
      if (mode === "estimate") {
        const fd = new FormData();
        files.forEach(f => fd.append("files", f));
        if (name) fd.append("name", name);
        const res = await visionApi.estimateFromIngredients(fd);
        setExtracted(res.data);
        setName(res.data.name || "");
        setServingSize(res.data.serving_size || "");
        setServingSizeG(res.data.serving_size_g != null ? String(res.data.serving_size_g) : "");
        setStep("reviewing");
      } else {
        const fd = new FormData();
        fd.append("file", file1);
        const res = await visionApi.extract(fd);
        setExtracted(res.data);
        setName(res.data.name || "");
        setServingSize(res.data.serving_size || "");
        setServingSizeG(res.data.serving_size_g != null ? String(res.data.serving_size_g) : "");
        setStep("reviewing");
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Extraction failed — please try again.");
    } finally {
      setLoading(false);
    }
  };

  // ── Save ──────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setLoading(true);
    try {
      if (mode === "estimate") {
        const fd = new FormData();
        files.forEach(f => fd.append("files", f));
        if (name) fd.append("name", name);
        await visionApi.estimateFromIngredients(fd);
      } else {
        const fd = new FormData();
        fd.append("file", file1);
        if (name) fd.append("name", name);
        await visionApi.extractAndSave(fd);
      }
      setStep("saved");
      setTimeout(onSaved, 1200);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed");
    } finally {
      setLoading(false);
    }
  };

  const isEstimate = mode === "estimate";
  const hasImages  = isEstimate ? files.length > 0 : !!file1;

  return (
    <ModalShell
      onClose={onClose}
      title={isEstimate ? "Estimate from Screenshot" : "Scan Nutrition Label"}
    >

      {/* ── Upload step ── */}
      {step === "upload" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            {isEstimate
              ? "Upload screenshots of an ingredient list, food package back, or meal-tracking app. Claude will estimate the nutrition profile. You can add up to 5 photos."
              : "Upload a photo of a nutrition facts label. Claude will read the exact values from the label."}
          </p>

          {/* ── Estimate mode: dynamic multi-photo grid ── */}
          {isEstimate && (
            <>
              {previews.length > 0 && (
                <div className="grid grid-cols-2 gap-2">
                  {previews.map((src, i) => (
                    <div key={i} className="relative">
                      <img
                        src={src}
                        alt={`Photo ${i + 1}`}
                        className="w-full h-32 object-cover rounded-xl border border-border"
                      />
                      <button
                        onClick={() => handleRemoveFile(i)}
                        className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-black/70 flex items-center justify-center text-white hover:bg-red-500/80"
                      >
                        <X size={11} />
                      </button>
                      <span className="absolute bottom-1.5 left-2 text-[10px] text-white font-semibold drop-shadow">
                        Photo {i + 1}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {files.length < 5 && (
                <label className="flex flex-col items-center justify-center gap-2 py-5 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-accent-blue transition-colors">
                  <div className="flex items-center gap-2 text-muted">
                    <Plus size={16} />
                    <span className="text-sm font-medium">
                      {files.length === 0 ? "Tap to add photos" : "Add another photo"}
                    </span>
                  </div>
                  {files.length === 0 && (
                    <span className="text-xs text-muted">Up to 5 images</span>
                  )}
                  {/* No capture attribute — allows photo library selection on iOS */}
                  <input
                    ref={addFileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={e => handleAddFile(e.target.files[0])}
                  />
                </label>
              )}
            </>
          )}

          {/* ── Label mode: single photo ── */}
          {!isEstimate && (
            <div>
              {preview1 ? (
                <div className="relative">
                  <img
                    src={preview1}
                    alt="Label"
                    className="w-full max-h-44 object-contain rounded-xl border border-border"
                  />
                  <button
                    onClick={() => {
                      setFile1(null);
                      setPreview1(null);
                      if (fileRef1.current) fileRef1.current.value = "";
                    }}
                    className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/70 flex items-center justify-center text-white hover:bg-red-500/80"
                  >
                    <X size={11} />
                  </button>
                </div>
              ) : (
                <label className="flex flex-col items-center justify-center gap-3 py-8 border-2 border-dashed border-border rounded-xl cursor-pointer hover:border-accent-blue transition-colors">
                  <Camera size={24} className="text-muted" />
                  <p className="text-sm font-medium">Tap to add label photo</p>
                  {/* No capture attribute — allows photo library on iOS */}
                  <input
                    ref={fileRef1}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={e => handleFile1(e.target.files[0])}
                  />
                </label>
              )}
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted">
              <Loader2 size={16} className="animate-spin" />
              {isEstimate ? "Estimating nutrition…" : "Extracting macros…"}
            </div>
          )}
          {error && <p className="text-accent-red text-sm">{error}</p>}

          <button
            onClick={handleExtract}
            disabled={!hasImages || loading}
            className="btn-primary flex items-center justify-center gap-2 py-3 disabled:opacity-40"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
            {isEstimate ? "Estimate Nutrition" : "Extract Nutrition Info"}
          </button>
        </div>
      )}

      {/* ── Review step ── */}
      {step === "reviewing" && extracted && (
        <div className="flex flex-col gap-4">
          {/* Photo thumbnails */}
          {isEstimate ? (
            previews.length > 0 && (
              <div className={`grid gap-2 ${previews.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                {previews.map((src, i) => (
                  <img
                    key={i}
                    src={src}
                    alt={`Photo ${i + 1}`}
                    className="w-full max-h-36 object-contain rounded-lg border border-border"
                  />
                ))}
              </div>
            )
          ) : (
            preview1 && (
              <img
                src={preview1}
                alt="Label"
                className="w-full max-h-36 object-contain rounded-lg border border-border"
              />
            )
          )}

          <div>
            <label className="text-xs text-muted mb-1 block font-semibold uppercase tracking-wide">Food Name</label>
            <input value={name} onChange={e => setName(e.target.value)} className="input" />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted mb-1 block font-semibold uppercase tracking-wide">Serving size (label)</label>
              <input value={servingSize} onChange={e => setServingSize(e.target.value)} className="input" placeholder="e.g. 1 cup (240mL)" />
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block font-semibold uppercase tracking-wide">Serving size (g)</label>
              <input
                type="number"
                value={servingSizeG}
                onChange={e => setServingSizeG(e.target.value)}
                className="input font-mono"
                placeholder="100"
                min="0.1"
                step="0.5"
              />
            </div>
          </div>

          {/* ── Macros ── */}
          <div className="card-sm flex flex-col gap-3">
            <p className="text-[10px] text-muted font-semibold uppercase tracking-wide">Macros</p>
            <div className="grid grid-cols-3 gap-y-3">
              {[
                { label: "Calories",    value: extracted.calories,       unit: "kcal", color: "#FF9500" },
                { label: "Protein",     value: extracted.protein_g,      unit: "g",    color: "#34C759" },
                { label: "Total Fat",   value: extracted.fat_g,          unit: "g",    color: "#FF3B30" },
                { label: "Sat. Fat",    value: extracted.sat_fat_g,      unit: "g",    color: null },
                { label: "Trans Fat",   value: extracted.trans_fat_g,    unit: "g",    color: null },
                { label: "Total Carbs", value: extracted.carbs_g,        unit: "g",    color: "#007AFF" },
                { label: "Fiber",       value: extracted.fiber_g,        unit: "g",    color: null },
                { label: "Sugars",      value: extracted.sugar_g,        unit: "g",    color: null },
                { label: "Added Sugar", value: extracted.added_sugar_g,  unit: "g",    color: null },
              ].map(({ label, value, unit, color }) => (
                <div key={label} className="flex flex-col">
                  <span className="text-[10px] text-muted">{label}</span>
                  <span className="text-sm font-mono font-semibold" style={{ color: color || "#111827" }}>
                    {value != null ? `${value}${unit}` : "–"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* ── Micronutrients ── */}
          <div className="card-sm flex flex-col gap-3">
            <p className="text-[10px] text-muted font-semibold uppercase tracking-wide">Micronutrients</p>
            <div className="grid grid-cols-3 gap-y-3">
              {[
                { label: "Sodium",      value: extracted.sodium_mg,      unit: "mg" },
                { label: "Cholesterol", value: extracted.cholesterol_mg, unit: "mg" },
                { label: "Potassium",   value: extracted.potassium_mg,   unit: "mg" },
                { label: "Calcium",     value: extracted.calcium_mg,     unit: "mg" },
                { label: "Iron",        value: extracted.iron_mg,        unit: "mg" },
                { label: "Vitamin D",   value: extracted.vitamin_d_mcg,  unit: "mcg" },
              ].map(({ label, value, unit }) => (
                <div key={label} className="flex flex-col">
                  <span className="text-[10px] text-muted">{label}</span>
                  <span className="text-sm font-mono font-semibold text-foreground">
                    {value != null ? `${value}${unit}` : "–"}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted">
            <span className="text-accent-green">●</span>
            Confidence: {(extracted.confidence * 100).toFixed(0)}%
            {isEstimate && <span className="text-muted/60">· AI estimate</span>}
          </div>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <div className="flex gap-2">
            <button onClick={() => setStep("upload")} className="btn-ghost flex-1">Retake</button>
            <button onClick={handleSave} disabled={loading} className="btn-primary flex-1 flex items-center justify-center gap-2">
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              Save to My Foods
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
