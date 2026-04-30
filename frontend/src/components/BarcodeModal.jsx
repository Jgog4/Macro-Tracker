/**
 * BarcodeModal — scan a product barcode → Open Food Facts lookup → review → save.
 *
 * Step 1 "scan":    Live camera view; ZXing decodes EAN/UPC barcodes in real time.
 *                   Falls back to a manual-entry field if camera access is denied.
 * Step 2 "review":  Shows the parsed nutrition. User can edit name & confirm.
 * Step 3 "saved":   Food saved to My Foods; onSaved(food) fires to open log screen.
 */
import { useState, useEffect, useRef } from "react";
import { visionApi, foodsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import { ScanLine, Loader2, Check, Upload, X, AlertCircle } from "lucide-react";

export default function BarcodeModal({ onClose, onSaved }) {
  const [step,       setStep]       = useState("scan");   // scan | review | saved
  const [barcode,    setBarcode]    = useState("");
  const [manualCode, setManualCode] = useState("");
  const [food,       setFood]       = useState(null);
  const [name,       setName]       = useState("");
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState("");
  const [cameraErr,  setCameraErr]  = useState("");

  const videoRef    = useRef(null);
  const scannerRef  = useRef(null);   // ZXing reader instance
  const detectedRef = useRef(false);  // prevent double-fire

  // ── Start ZXing camera scanner ────────────────────────────────────────────
  useEffect(() => {
    if (step !== "scan") return;
    detectedRef.current = false;
    let cancelled = false;

    async function startScanner() {
      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        const reader = new BrowserMultiFormatReader();
        scannerRef.current = reader;

        // Get available video devices and pick the back camera
        const devices = await BrowserMultiFormatReader.listVideoInputDevices();
        const backCam = devices.find(d =>
          /back|rear|environment/i.test(d.label)
        ) || devices[devices.length - 1];   // last device is usually back cam

        const deviceId = backCam?.deviceId ?? undefined;
        await reader.decodeFromVideoDevice(deviceId, videoRef.current, (result, err) => {
          if (cancelled || detectedRef.current) return;
          if (result) {
            detectedRef.current = true;
            handleBarcode(result.getText());
          }
        });
      } catch (e) {
        if (!cancelled) {
          setCameraErr(
            e?.name === "NotAllowedError"
              ? "Camera access denied. Enter the barcode manually below."
              : "Camera unavailable. Enter the barcode manually below."
          );
        }
      }
    }

    startScanner();

    return () => {
      cancelled = true;
      try { scannerRef.current?.reset(); } catch { /* ignore */ }
    };
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Lookup barcode in Open Food Facts ─────────────────────────────────────
  const handleBarcode = async (code) => {
    setBarcode(code);
    setLoading(true);
    setError("");
    try { scannerRef.current?.reset(); } catch { /* ignore */ }

    try {
      const res = await visionApi.lookupBarcode(code);
      setFood(res.data);
      setName(res.data.name || "");
      setStep("review");
    } catch (e) {
      const detail = e.response?.data?.detail || "";
      if (e.response?.status === 404) {
        setError(`Barcode ${code} not found in the Open Food Facts database. Try scanning again or enter it manually.`);
      } else {
        setError(detail || "Lookup failed — please try again.");
      }
      detectedRef.current = false;   // allow re-scan
    } finally {
      setLoading(false);
    }
  };

  // ── Save confirmed food ───────────────────────────────────────────────────
  const handleSave = async () => {
    if (!food) return;
    setLoading(true);
    setError("");
    try {
      const res = await foodsApi.create({
        source:            "custom",
        name:              name.trim() || food.name,
        brand:             food.brand || null,
        serving_size_desc: food.serving_size_desc || null,
        serving_size_g:    food.serving_size_g    || null,
        calories:          food.calories,
        protein_g:         food.protein_g,
        fat_g:             food.fat_g,
        carbs_g:           food.carbs_g,
        sat_fat_g:         food.sat_fat_g         ?? null,
        trans_fat_g:       food.trans_fat_g        ?? null,
        fiber_g:           food.fiber_g            ?? null,
        sugar_g:           food.sugar_g            ?? null,
        sodium_mg:         food.sodium_mg          ?? null,
        cholesterol_mg:    food.cholesterol_mg     ?? null,
        potassium_mg:      food.potassium_mg       ?? null,
      });
      setStep("saved");
      setTimeout(() => onSaved(res.data), 1200);
    } catch (e) {
      setError(e.response?.data?.detail || "Save failed — please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Scan Barcode">

      {/* ── Scan step ── */}
      {step === "scan" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            Point your camera at the barcode on the product packaging.
          </p>

          {/* Camera viewfinder */}
          <div className="relative w-full overflow-hidden rounded-2xl bg-black"
               style={{ aspectRatio: "4/3" }}>
            <video
              ref={videoRef}
              className="w-full h-full object-cover"
              muted
              playsInline
              autoPlay
            />
            {/* Scanning reticle */}
            {!cameraErr && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-56 h-28 relative">
                  {/* Corner brackets */}
                  {[
                    "top-0 left-0 border-t-2 border-l-2 rounded-tl-lg",
                    "top-0 right-0 border-t-2 border-r-2 rounded-tr-lg",
                    "bottom-0 left-0 border-b-2 border-l-2 rounded-bl-lg",
                    "bottom-0 right-0 border-b-2 border-r-2 rounded-br-lg",
                  ].map((cls, i) => (
                    <div key={i} className={`absolute w-6 h-6 border-white ${cls}`} />
                  ))}
                  {/* Animated scan line */}
                  <div className="absolute inset-x-2 h-0.5 bg-accent-blue/80 animate-scan-line" />
                </div>
              </div>
            )}
          </div>

          {/* Camera error / manual entry */}
          {cameraErr && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-50 text-amber-800">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <p className="text-xs">{cameraErr}</p>
            </div>
          )}

          {/* Loading overlay */}
          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted">
              <Loader2 size={15} className="animate-spin" />
              Looking up barcode…
            </div>
          )}
          {error && (
            <p className="text-accent-red text-xs flex items-start gap-1.5">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              {error}
            </p>
          )}

          {/* Manual barcode entry */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">
              Or enter barcode manually
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                value={manualCode}
                onChange={e => setManualCode(e.target.value)}
                placeholder="e.g. 0 62700 02520 7"
                className="input flex-1 font-mono"
              />
              <button
                onClick={() => manualCode.trim() && handleBarcode(manualCode.trim())}
                disabled={!manualCode.trim() || loading}
                className="btn-primary px-4 disabled:opacity-40"
              >
                <ScanLine size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Review step ── */}
      {step === "review" && food && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-green-50">
            <Check size={13} className="text-green-600 shrink-0" />
            <p className="text-xs text-green-700 font-medium">
              Found · barcode {barcode}
            </p>
          </div>

          <div>
            <label className="text-xs text-muted mb-1 block font-semibold uppercase tracking-wide">Food Name</label>
            <input value={name} onChange={e => setName(e.target.value)} className="input" />
          </div>

          {food.serving_size_desc && (
            <p className="text-xs text-muted">
              Serving: <span className="text-foreground font-medium">{food.serving_size_desc}</span>
              {food.serving_size_g && ` (${food.serving_size_g}g)`}
            </p>
          )}

          {/* Macros */}
          <div className="card-sm flex flex-col gap-3">
            <p className="text-[10px] text-muted font-semibold uppercase tracking-wide">
              Macros {food.serving_size_g ? `per serving (${food.serving_size_g}g)` : "per 100g"}
            </p>
            <div className="grid grid-cols-3 gap-y-3">
              {[
                { label: "Calories",    value: food.calories,    unit: "kcal", color: "#FF9500" },
                { label: "Protein",     value: food.protein_g,   unit: "g",    color: "#34C759" },
                { label: "Total Fat",   value: food.fat_g,       unit: "g",    color: "#FF3B30" },
                { label: "Sat. Fat",    value: food.sat_fat_g,   unit: "g",    color: null },
                { label: "Trans Fat",   value: food.trans_fat_g, unit: "g",    color: null },
                { label: "Total Carbs", value: food.carbs_g,     unit: "g",    color: "#007AFF" },
                { label: "Fiber",       value: food.fiber_g,     unit: "g",    color: null },
                { label: "Sugars",      value: food.sugar_g,     unit: "g",    color: null },
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

          {/* Micronutrients */}
          <div className="card-sm flex flex-col gap-3">
            <p className="text-[10px] text-muted font-semibold uppercase tracking-wide">Micronutrients</p>
            <div className="grid grid-cols-3 gap-y-3">
              {[
                { label: "Sodium",      value: food.sodium_mg,     unit: "mg" },
                { label: "Cholesterol", value: food.cholesterol_mg, unit: "mg" },
                { label: "Potassium",   value: food.potassium_mg,   unit: "mg" },
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

          <p className="text-[11px] text-muted">
            Source: <span className="font-medium">Open Food Facts</span>
          </p>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <div className="flex gap-2">
            <button
              onClick={() => { setStep("scan"); setError(""); }}
              className="btn-ghost flex-1"
            >
              <X size={13} className="inline mr-1" />
              Rescan
            </button>
            <button
              onClick={handleSave}
              disabled={loading}
              className="btn-primary flex-1 flex items-center justify-center gap-2"
            >
              {loading
                ? <Loader2 size={14} className="animate-spin" />
                : <Upload size={14} />}
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
          <p className="text-sm text-muted">Opening log screen…</p>
        </div>
      )}
    </ModalShell>
  );
}
