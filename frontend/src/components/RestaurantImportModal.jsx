/**
 * Import a restaurant's published nutrition PDF from a link.
 *
 * Two steps, like the recipe importer: paste a link, then review what was read
 * before anything reaches the library. The review step matters more here than
 * elsewhere — a nutrition guide is a table, and the importer works out which
 * column is which from the document itself, so showing the detected columns and
 * a sample of rows is what lets the user catch a misread before it becomes 500
 * wrong foods.
 *
 * Rows whose macros do not reconcile with their printed calories arrive
 * separately as `flagged` and start deselected. They are usually the
 * publisher's own typo, or a drink whose calories include alcohol.
 */
import { useMemo, useState } from "react";
import { Loader2, FileText, AlertTriangle, Check } from "lucide-react";
import { restaurantImportApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const COLUMN_LABEL = {
  calories: "Calories", protein_g: "Protein", carbs_g: "Carbs", fat_g: "Fat",
  sat_fat_g: "Sat fat", trans_fat_g: "Trans fat", fiber_g: "Fibre",
  sugar_g: "Sugar", sodium_mg: "Sodium", cholesterol_mg: "Cholesterol",
  caffeine_mg: "Caffeine", serving_size_g: "Serving (g)",
};

function Row({ item, checked, onToggle }) {
  const v = item.values || {};
  return (
    <label className="flex items-start gap-3 py-2 border-b border-surface-3 last:border-0">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-1 h-4 w-4 accent-accent-blue shrink-0"
      />
      <span className="flex-1 min-w-0">
        <span className="block text-sm text-foreground truncate">{item.name}</span>
        <span className="block text-xs text-muted">
          {Math.round(v.calories)} kcal
          {v.protein_g != null && ` · P ${v.protein_g}`}
          {v.carbs_g   != null && ` · C ${v.carbs_g}`}
          {v.fat_g     != null && ` · F ${v.fat_g}`}
          {v.serving_size_g != null && ` · ${v.serving_size_g} g`}
        </span>
        {item.reason && (
          <span className="block text-xs text-accent-orange mt-0.5">{item.reason}</span>
        )}
      </span>
    </label>
  );
}

export default function RestaurantImportModal({ onClose, onSaved }) {
  const [step, setStep]   = useState("input");      // input | review
  const [url, setUrl]     = useState("");
  const [brand, setBrand] = useState("");
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState("");

  const [draft, setDraft]     = useState(null);
  const [skipped, setSkipped] = useState({});       // name -> true when excluded
  const [saving, setSaving]   = useState(false);

  const allRows = useMemo(
    () => (draft ? [...draft.items, ...draft.flagged] : []),
    [draft],
  );
  const selected = useMemo(
    () => allRows.filter(r => !skipped[r.name]),
    [allRows, skipped],
  );

  const runPreview = async () => {
    if (!url.trim()) return;
    setBusy(true); setError("");
    try {
      const res = await restaurantImportApi.preview({ url: url.trim(), brand: brand.trim() || null });
      setDraft(res.data);
      setBrand(res.data.brand || "");
      // Flagged rows did not reconcile, so they are opt-in rather than opt-out.
      setSkipped(Object.fromEntries(res.data.flagged.map(f => [f.name, true])));
      setStep("review");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not read that PDF.");
    } finally {
      setBusy(false);
    }
  };

  const runSave = async () => {
    if (!brand.trim() || !selected.length) return;
    setSaving(true); setError("");
    try {
      const res = await restaurantImportApi.save({
        brand: brand.trim(),
        items: selected.map(r => ({ name: r.name, values: r.values })),
      });
      onSaved?.(res.data);
      onClose();
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not save these items.");
      setSaving(false);
    }
  };

  const toggle = (name) => setSkipped(s => ({ ...s, [name]: !s[name] }));
  const setAll = (rows, skip) =>
    setSkipped(s => ({ ...s, ...Object.fromEntries(rows.map(r => [r.name, skip])) }));

  /* ── input ─────────────────────────────────────────────────────────────── */
  if (step === "input") {
    return (
      <ModalShell onClose={onClose} title="Import a restaurant guide">
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted">
            Paste a link to a restaurant’s published nutrition PDF. The menu items
            are read from it and added under that restaurant.
          </p>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted">PDF link</span>
            <input
              type="url"
              inputMode="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://example.com/nutrition-guide.pdf"
              className="w-full rounded-xl bg-surface-2 px-3 py-2.5 text-sm text-foreground outline-none"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted">
              Restaurant name <span className="font-normal">(optional — guessed from the link)</span>
            </span>
            <input
              value={brand}
              onChange={e => setBrand(e.target.value)}
              placeholder="e.g. Panera Bread"
              className="w-full rounded-xl bg-surface-2 px-3 py-2.5 text-sm text-foreground outline-none"
            />
          </label>

          {error && <p className="text-sm text-accent-red">{error}</p>}

          <button
            onClick={runPreview}
            disabled={busy || !url.trim()}
            className="flex items-center justify-center gap-2 rounded-xl bg-accent-blue px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy
              ? <><Loader2 size={16} className="animate-spin" /> Reading the guide…</>
              : <><FileText size={16} /> Read guide</>}
          </button>
          {busy && (
            <p className="text-center text-xs text-muted">
              Large guides take a few seconds.
            </p>
          )}
        </div>
      </ModalShell>
    );
  }

  /* ── review ────────────────────────────────────────────────────────────── */
  const detected = (draft.columns || []).map(c => COLUMN_LABEL[c.field]).filter(Boolean);

  return (
    <ModalShell onClose={onClose} title={`Review — ${draft.items.length + draft.flagged.length} items`}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted">Add under restaurant</span>
          <input
            value={brand}
            onChange={e => setBrand(e.target.value)}
            className="w-full rounded-xl bg-surface-2 px-3 py-2.5 text-sm font-semibold text-foreground outline-none"
          />
        </label>

        <div className="rounded-xl bg-surface-2 p-3">
          <p className="text-xs font-medium text-muted mb-1">
            Columns read from the guide ({draft.pages} pages)
          </p>
          <p className="text-xs text-foreground">{detected.join(" · ")}</p>
          {(draft.warnings || []).map((w, i) => (
            <p key={i} className="mt-2 flex gap-1.5 text-xs text-muted">
              <AlertTriangle size={13} className="mt-0.5 shrink-0 text-accent-orange" />
              {w}
            </p>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-muted">{selected.length} selected</span>
          <span className="flex gap-3 text-xs">
            <button onClick={() => setAll(allRows, false)} className="text-accent-blue">Select all</button>
            <button onClick={() => setAll(allRows, true)}  className="text-accent-blue">Clear</button>
          </span>
        </div>

        <div className="max-h-[38vh] overflow-y-auto rounded-xl bg-surface-1 px-3">
          {draft.items.map(item => (
            <Row key={item.name} item={item}
                 checked={!skipped[item.name]} onToggle={() => toggle(item.name)} />
          ))}
        </div>

        {draft.flagged.length > 0 && (
          <div className="flex flex-col gap-1">
            <p className="flex items-center gap-1.5 text-xs font-medium text-accent-orange">
              <AlertTriangle size={13} />
              {draft.flagged.length} didn’t add up
            </p>
            <p className="text-xs text-muted">
              Their macros don’t match their printed calories — usually a mistake in
              the guide, or a drink containing alcohol. Off by default.
            </p>
            <div className="mt-1 max-h-[22vh] overflow-y-auto rounded-xl bg-surface-1 px-3">
              {draft.flagged.map(item => (
                <Row key={item.name} item={item}
                     checked={!skipped[item.name]} onToggle={() => toggle(item.name)} />
              ))}
            </div>
          </div>
        )}

        {error && <p className="text-sm text-accent-red">{error}</p>}

        <div className="flex gap-2">
          <button
            onClick={() => { setStep("input"); setError(""); }}
            className="rounded-xl bg-surface-2 px-4 py-3 text-sm font-semibold text-foreground"
          >
            Back
          </button>
          <button
            onClick={runSave}
            disabled={saving || !selected.length || !brand.trim()}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent-blue px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"
          >
            {saving
              ? <><Loader2 size={16} className="animate-spin" /> Adding…</>
              : <><Check size={16} /> Add {selected.length} items</>}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
