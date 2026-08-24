/**
 * Export — download your data as CSV.
 *
 * Uses blob downloads (not plain <a href>) so exports keep working once
 * auth headers are added to the API client.
 */
import { useState } from "react";
import { Download, Loader2, FileArchive, Check } from "lucide-react";
import { exportApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const DATASETS = [
  { key: "food_log",           label: "Food log",          desc: "Every item you've logged — one row each" },
  { key: "daily_totals",       label: "Daily totals",      desc: "One row per day: calories and macros" },
  { key: "foods",              label: "Food library",      desc: "My Foods + restaurant items, full nutrition" },
  { key: "recipes",            label: "Recipes",           desc: "Recipe totals and serving sizes" },
  { key: "recipe_ingredients", label: "Recipe components", desc: "What's in each recipe" },
  { key: "targets",            label: "Macro targets",     desc: "Your calorie and macro goals" },
];

function saveBlob(data, filename) {
  const url = URL.createObjectURL(new Blob([data]));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke late so iOS Safari has time to start the download
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export default function ExportModal({ onClose }) {
  const [busy, setBusy]   = useState(null);   // key currently downloading
  const [done, setDone]   = useState([]);
  const [error, setError] = useState("");

  const today = new Date().toISOString().slice(0, 10);

  const grab = async (key, label) => {
    setBusy(key); setError("");
    try {
      if (key === "__zip") {
        const res = await exportApi.zip();
        saveBlob(res.data, `macro-tracker-export-${today}.zip`);
      } else {
        const res = await exportApi.csv(key);
        saveBlob(res.data, `${key}_${today}.csv`);
      }
      setDone((d) => [...d, key]);
    } catch (e) {
      setError(
        !e.response ? "Network error — check your connection."
                    : `Couldn't export ${label} (${e.response.status}).`
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <ModalShell onClose={onClose} title="Export Data">
      <div className="flex flex-col gap-4">
        <p className="text-[11px] text-muted -mt-1">
          CSV opens in Excel or Numbers and stays readable forever — a backup that
          doesn't depend on this app existing.
        </p>

        {/* Everything at once */}
        <button
          onClick={() => grab("__zip", "all data")}
          disabled={busy !== null}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
        >
          {busy === "__zip"
            ? <Loader2 size={15} className="animate-spin" />
            : done.includes("__zip") ? <Check size={15} /> : <FileArchive size={15} />}
          Download Everything (ZIP)
        </button>

        <div className="flex items-center gap-2">
          <div className="flex-1 h-px bg-surface-3" />
          <span className="text-[10px] text-muted uppercase tracking-wide">or pick one</span>
          <div className="flex-1 h-px bg-surface-3" />
        </div>

        {/* Individual files */}
        <div className="card-no-pad divide-y divide-surface-3">
          {DATASETS.map(({ key, label, desc }) => (
            <button
              key={key}
              onClick={() => grab(key, label)}
              disabled={busy !== null}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-2 transition-colors disabled:opacity-40"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">{label}</p>
                <p className="text-[11px] text-muted mt-0.5">{desc}</p>
              </div>
              {busy === key
                ? <Loader2 size={15} className="animate-spin text-muted shrink-0" />
                : done.includes(key)
                  ? <Check size={15} className="text-accent-green shrink-0" />
                  : <Download size={15} className="text-accent-blue shrink-0" />}
            </button>
          ))}
        </div>

        {error && <p className="text-accent-red text-xs">{error}</p>}

        <p className="text-[10px] text-muted text-center">
          On iPhone, downloads land in Files → Downloads.
        </p>
      </div>
    </ModalShell>
  );
}
