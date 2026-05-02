/**
 * BarcodeModal — scan a product barcode → Open Food Facts lookup → log directly.
 *
 * Step 1 "scan":   Live camera view with ZXing; manual-entry fallback if camera denied.
 * Step 2 "review": Edit name, choose meal/quantity/time, toggle "Save to My Foods".
 *                  Logs to diary directly — no forced library save.
 * Step 3 "done":   Confirmation, then onLogged() fires to refresh the dashboard.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { format } from "date-fns";
import { visionApi, foodsApi, mealsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";
import {
  ScanLine, Loader2, Check, X, AlertCircle, ChevronDown,
} from "lucide-react";

function nowTimeStr() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}

function buildServingOpts(food) {
  const opts = [];
  if (food?.serving_size_g) {
    const raw = (food.serving_size_desc || "").trim();
    const isRawG = /^\d+\.?\d*\s*(g|ml)$/i.test(raw);
    opts.push({
      id: "serving",
      label: (!isRawG && raw) ? raw : "serving",
      gramsEach: food.serving_size_g,
    });
  }
  opts.push({ id: "g", label: "g", gramsEach: 1 });
  return opts;
}

export default function BarcodeModal({ dateStr, onClose, onLogged }) {
  const [step,          setStep]          = useState("scan");
  const [manualCode,    setManualCode]    = useState("");
  const [barcode,       setBarcode]       = useState("");
  const [food,          setFood]          = useState(null);

  // log fields
  const [name,          setName]          = useState("");
  const [mealNumber,    setMealNumber]    = useState(1);
  const [amount,        setAmount]        = useState("1");
  const [servingOpts,   setServingOpts]   = useState([]);
  const [servingOpt,    setServingOpt]    = useState(null);
  const [showPicker,    setShowPicker]    = useState(false);
  const [time,          setTime]          = useState(nowTimeStr);
  const [mealTimes,     setMealTimes]     = useState({});
  const [timeEdited,    setTimeEdited]    = useState(false);
  const [saveToLibrary, setSaveToLibrary] = useState(false);

  const [loading,       setLoading]       = useState(false);
  const [logging,       setLogging]       = useState(false);
  const [error,         setError]         = useState("");
  const [cameraErr,     setCameraErr]     = useState("");

  const videoRef    = useRef(null);
  const scannerRef  = useRef(null);
  const detectedRef = useRef(false);

  // ── Stop camera stream completely ─────────────────────────────────────────
  const stopCamera = useCallback(() => {
    try { scannerRef.current?.reset(); } catch { /* ignore */ }
    const video = videoRef.current;
    if (video?.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop());
      video.srcObject = null;
    }
  }, []);

  // Stop camera when modal unmounts (user taps × or navigates away)
  useEffect(() => () => stopCamera(), [stopCamera]);

  // ── Start ZXing scanner ───────────────────────────────────────────────────
  useEffect(() => {
    if (step !== "scan") return;
    detectedRef.current = false;
    let cancelled = false;

    async function start() {
      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        const reader = new BrowserMultiFormatReader();
        scannerRef.current = reader;

        const devices  = await BrowserMultiFormatReader.listVideoInputDevices();
        const backCam  = devices.find(d => /back|rear|environment/i.test(d.label))
                      ?? devices[devices.length - 1];

        await reader.decodeFromVideoDevice(
          backCam?.deviceId,
          videoRef.current,
          (result, err) => {
            if (cancelled || detectedRef.current) return;
            if (result) {
              detectedRef.current = true;
              handleBarcode(result.getText());
            }
          }
        );
      } catch (e) {
        if (!cancelled) {
          setCameraErr(
            e?.name === "NotAllowedError"
              ? "Camera access denied — enter the barcode number below."
              : "Camera unavailable — enter the barcode number below."
          );
        }
      }
    }

    start();
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [step, stopCamera]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Fetch today's meal times for auto-fill ────────────────────────────────
  useEffect(() => {
    if (!dateStr) return;
    mealsApi.getDay(dateStr).then(res => {
      const map = {};
      (res.data?.meals || []).forEach(m => {
        if (m.logged_at) {
          const d = new Date(m.logged_at);
          map[m.meal_number] = `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
        }
      });
      setMealTimes(map);
    }).catch(() => {});
  }, [dateStr]);

  // Auto-fill time when meal or fetched times change
  useEffect(() => {
    if (timeEdited) return;
    setTime(mealTimes[mealNumber] || nowTimeStr());
  }, [mealNumber, mealTimes]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Look up barcode in Open Food Facts ───────────────────────────────────
  const handleBarcode = async (code) => {
    setBarcode(code);
    setLoading(true);
    setError("");
    stopCamera();

    try {
      const res = await visionApi.lookupBarcode(code);
      const f   = res.data;
      setFood(f);
      setName(f.name || "");

      const opts = buildServingOpts(f);
      setServingOpts(opts);
      setServingOpt(opts[0]);
      setAmount(opts[0].id === "g" ? "100" : "1");
      setStep("review");
    } catch (e) {
      if (e.response?.status === 404) {
        setError(`Barcode ${code} not found in Open Food Facts. Try again or enter manually.`);
      } else {
        setError(e.response?.data?.detail || "Lookup failed — please try again.");
      }
      detectedRef.current = false;
    } finally {
      setLoading(false);
    }
  };

  // ── Log to diary ──────────────────────────────────────────────────────────
  const handleLog = async () => {
    if (!food) return;
    setLogging(true);
    setError("");
    try {
      // Always create an ingredient so we have an ID to log
      const source = saveToLibrary ? "custom" : "barcode";
      const saved  = await foodsApi.create({
        source,
        name:              name.trim() || food.name,
        brand:             food.brand             ?? null,
        serving_size_desc: food.serving_size_desc ?? null,
        serving_size_g:    food.serving_size_g    ?? null,
        calories:          food.calories,
        protein_g:         food.protein_g,
        fat_g:             food.fat_g,
        carbs_g:           food.carbs_g,
        sat_fat_g:         food.sat_fat_g         ?? null,
        trans_fat_g:       food.trans_fat_g       ?? null,
        fiber_g:           food.fiber_g           ?? null,
        sugar_g:           food.sugar_g           ?? null,
        sodium_mg:         food.sodium_mg         ?? null,
        cholesterol_mg:    food.cholesterol_mg    ?? null,
        potassium_mg:      food.potassium_mg      ?? null,
      });

      const amountNum = parseFloat(amount) || 0;
      const qtyNum    = amountNum * (servingOpt?.gramsEach ?? 1);

      const [h, m] = time.split(":").map(Number);
      const loggedAt = new Date(
        `${dateStr}T${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:00`
      );

      await mealsApi.logFood({
        log_date:    dateStr,
        meal_number: mealNumber,
        logged_at:   loggedAt.toISOString(),
        items: [{ ingredient_id: saved.data.id, quantity_g: qtyNum }],
      });

      setStep("done");
      setTimeout(() => onLogged(), 1000);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to log — please try again.");
    } finally {
      setLogging(false);
    }
  };

  // ── Derived live macros ───────────────────────────────────────────────────
  const amountNum = parseFloat(amount) || 0;
  const qtyNum    = amountNum * (servingOpt?.gramsEach ?? 1);
  const baseG     = food?.serving_size_g || (qtyNum || 100);
  const ratio     = qtyNum / baseG;
  const live = food ? {
    calories: (food.calories  || 0) * ratio,
    protein:  (food.protein_g || 0) * ratio,
    carbs:    (food.carbs_g   || 0) * ratio,
    fat:      (food.fat_g     || 0) * ratio,
  } : null;

  return (
    <ModalShell onClose={onClose} title="Scan Barcode">

      {/* ── Scan step ── */}
      {step === "scan" && (
        <div className="flex flex-col gap-4">
          <p className="text-xs text-muted">
            Point your camera at the barcode on the product packaging.
          </p>

          {/* Viewfinder */}
          <div className="relative w-full overflow-hidden rounded-2xl bg-black"
               style={{ aspectRatio: "4/3" }}>
            <video ref={videoRef} className="w-full h-full object-cover"
                   muted playsInline autoPlay />
            {!cameraErr && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-56 h-28 relative">
                  {[
                    "top-0 left-0 border-t-2 border-l-2 rounded-tl-lg",
                    "top-0 right-0 border-t-2 border-r-2 rounded-tr-lg",
                    "bottom-0 left-0 border-b-2 border-l-2 rounded-bl-lg",
                    "bottom-0 right-0 border-b-2 border-r-2 rounded-br-lg",
                  ].map((cls, i) => (
                    <div key={i} className={`absolute w-6 h-6 border-white ${cls}`} />
                  ))}
                  <div className="absolute inset-x-2 h-0.5 bg-accent-blue/80 animate-scan-line" />
                </div>
              </div>
            )}
          </div>

          {cameraErr && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl bg-amber-50 text-amber-800">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <p className="text-xs">{cameraErr}</p>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 text-sm text-muted">
              <Loader2 size={15} className="animate-spin" /> Looking up barcode…
            </div>
          )}
          {error && (
            <p className="text-accent-red text-xs flex items-start gap-1.5">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />{error}
            </p>
          )}

          {/* Manual entry */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">
              Or enter barcode manually
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                value={manualCode}
                onChange={e => setManualCode(e.target.value)}
                placeholder="e.g. 062700025207"
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

      {/* ── Review / log step ── */}
      {step === "review" && food && (
        <div className="flex flex-col gap-4">
          {/* Barcode badge */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-green-50">
            <Check size={13} className="text-green-600 shrink-0" />
            <p className="text-xs text-green-700 font-medium truncate">
              {barcode} · Open Food Facts
            </p>
          </div>

          {/* Food name */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">
              Food Name
            </label>
            <input value={name} onChange={e => setName(e.target.value)} className="input" />
          </div>

          {/* Meal selector */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1.5 block">Meal</label>
            <div className="grid grid-cols-6 gap-1">
              {[1,2,3,4,5,6].map(n => (
                <button key={n}
                  onClick={() => { setTimeEdited(false); setMealNumber(n); }}
                  className={`py-2 rounded-xl text-sm font-bold transition-colors
                    ${n === mealNumber
                      ? "bg-accent-blue text-white shadow-sm"
                      : "bg-surface-2 text-muted hover:bg-surface-3"}`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Amount + serving */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-2 block">Amount</label>
            <div className="flex gap-2 items-stretch">
              <input
                type="number"
                value={amount}
                onChange={e => setAmount(e.target.value)}
                className="input font-mono w-28 shrink-0"
                min="0.1"
                step={servingOpt?.id === "g" ? "5" : "0.5"}
              />
              <button
                onClick={() => setShowPicker(p => !p)}
                className="flex-1 flex items-center justify-between gap-1 px-3 py-2.5 rounded-xl border border-surface-3 bg-surface-1 text-sm font-medium text-foreground hover:bg-surface-2 transition-colors"
              >
                <span className="truncate text-left">
                  {servingOpt?.id === "g"
                    ? "g"
                    : `${servingOpt?.label} — ${servingOpt?.gramsEach}g`}
                </span>
                <ChevronDown size={14} className={`text-muted shrink-0 transition-transform ${showPicker ? "rotate-180" : ""}`} />
              </button>
            </div>

            {showPicker && (
              <div className="mt-1 rounded-xl border border-surface-3 bg-white shadow-lg overflow-hidden">
                {servingOpts.map((opt, i) => (
                  <button key={opt.id}
                    onClick={() => {
                      if (servingOpt && servingOpt.id !== opt.id) {
                        const currentG = (parseFloat(amount) || 0) * servingOpt.gramsEach;
                        const newAmt   = opt.id === "g"
                          ? Math.round(currentG * 10) / 10
                          : Math.round((currentG / opt.gramsEach) * 100) / 100;
                        setAmount(String(newAmt));
                      }
                      setServingOpt(opt);
                      setShowPicker(false);
                    }}
                    className={`w-full flex items-center justify-between px-4 py-3 text-sm text-left transition-colors
                      ${i > 0 ? "border-t border-surface-2" : ""}
                      ${servingOpt?.id === opt.id ? "bg-blue-50 text-accent-blue font-semibold" : "hover:bg-surface-1 text-foreground"}`}
                  >
                    <span>{opt.id === "g" ? "g" : opt.label}</span>
                    {opt.id !== "g" && (
                      <span className="text-xs text-muted ml-2 shrink-0">{opt.gramsEach}g each</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {servingOpt?.id !== "g" && amountNum > 0 && (
              <p className="text-[11px] text-muted mt-1.5">
                = {Math.round(qtyNum * 10) / 10}g logged
              </p>
            )}
          </div>

          {/* Time */}
          <div>
            <label className="text-xs font-semibold text-muted uppercase tracking-wide mb-1 block">Time</label>
            <input type="time" value={time}
              onChange={e => { setTime(e.target.value); setTimeEdited(true); }}
              className="input font-mono" />
          </div>

          {/* Live macros */}
          <div className="bg-surface-2 rounded-2xl p-4">
            <div className="grid grid-cols-4 gap-2">
              {[
                { label: "Calories", value: live?.calories, unit: "kcal", color: "#FF9500" },
                { label: "Protein",  value: live?.protein,  unit: "g",    color: "#34C759" },
                { label: "Carbs",    value: live?.carbs,    unit: "g",    color: "#007AFF" },
                { label: "Fat",      value: live?.fat,      unit: "g",    color: "#FF3B30" },
              ].map(({ label, value, unit, color }) => (
                <div key={label} className="flex flex-col items-center">
                  <span className="text-base font-bold font-mono" style={{ color }}>
                    {value != null ? (value >= 10 ? Math.round(value) : value.toFixed(1)) : "—"}
                  </span>
                  <span className="text-[10px] text-muted mt-0.5">{unit}</span>
                  <span className="text-[9px] text-subtle">{label}</span>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-muted mt-2 text-center">
              {amountNum > 0
                ? servingOpt?.id === "g"
                  ? `${qtyNum}g`
                  : `${amountNum} × ${servingOpt?.gramsEach}g = ${Math.round(qtyNum * 10) / 10}g`
                : "—"}
            </p>
          </div>

          {/* Save to My Foods toggle */}
          <label className="flex items-center gap-3 cursor-pointer select-none">
            <div
              onClick={() => setSaveToLibrary(v => !v)}
              className={`w-11 h-6 rounded-full relative transition-colors ${saveToLibrary ? "bg-accent-blue" : "bg-surface-3"}`}
            >
              <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${saveToLibrary ? "translate-x-5" : "translate-x-0.5"}`} />
            </div>
            <span className="text-sm text-foreground">Also save to My Foods</span>
          </label>

          {error && <p className="text-accent-red text-xs">{error}</p>}

          <div className="flex gap-2">
            <button onClick={() => { setStep("scan"); setError(""); }} className="btn-ghost flex-1">
              <X size={13} className="inline mr-1" />Rescan
            </button>
            <button
              onClick={handleLog}
              disabled={logging || qtyNum <= 0}
              className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-40"
            >
              {logging ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              Log to Meal {mealNumber}
            </button>
          </div>
        </div>
      )}

      {/* ── Done step ── */}
      {step === "done" && (
        <div className="flex flex-col items-center gap-3 py-8">
          <div className="w-12 h-12 rounded-full bg-accent-green/20 flex items-center justify-center">
            <Check size={24} className="text-accent-green" />
          </div>
          <p className="font-medium">Logged to Meal {mealNumber}</p>
          {saveToLibrary && <p className="text-sm text-muted">Saved to My Foods too</p>}
        </div>
      )}
    </ModalShell>
  );
}
