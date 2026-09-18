/**
 * Rename or delete a whole restaurant.
 *
 * Delete asks the server what the damage would be before asking the user,
 * because the two consequences are not equal and a bare "are you sure" hides
 * the one that matters. Logged meals survive: mt_meal_log_items keeps its own
 * frozen copy of the macros, so past days keep their totals. Recipes do not:
 * that foreign key cascades, so a recipe built on one of these items loses the
 * line and silently changes its totals. If a recipe is affected it is named
 * here, and deleting takes a second confirmation.
 */
import { useEffect, useState } from "react";
import { Loader2, AlertTriangle, Trash2, Check } from "lucide-react";
import { foodsApi } from "../api/client";
import { ModalShell } from "./AddFoodModal";

export default function RestaurantBrandModal({ brand, mode, onClose, onDone }) {
  const [name, setName]     = useState(brand);
  const [usage, setUsage]   = useState(null);
  const [busy, setBusy]     = useState(false);
  const [error, setError]   = useState("");
  const [armed, setArmed]   = useState(false);   // second confirm, recipes only

  useEffect(() => {
    if (mode !== "delete") return;
    let live = true;
    (async () => {
      try {
        const res = await foodsApi.brandUsage(brand);
        if (live) setUsage(res.data);
      } catch {
        if (live) setUsage({ items: null, logged_items: 0, recipes: [] });
      }
    })();
    return () => { live = false; };
  }, [brand, mode]);

  const rename = async () => {
    const next = name.trim();
    if (!next || next === brand) return onClose();
    setBusy(true); setError("");
    try {
      await foodsApi.renameBrand(brand, next);
      onDone(`Renamed to ${next}`);
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not rename that restaurant.");
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true); setError("");
    try {
      const res = await foodsApi.deleteBrand(brand);
      onDone(`Deleted ${brand} (${res.data.deleted} items)`);
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not delete that restaurant.");
      setBusy(false);
    }
  };

  if (mode === "rename") {
    return (
      <ModalShell onClose={onClose} title="Rename restaurant">
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted">Restaurant name</span>
            <input
              value={name}
              autoFocus
              onChange={e => setName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && rename()}
              className="w-full rounded-xl bg-surface-2 px-3 py-2.5 text-sm text-foreground outline-none"
            />
          </label>
          <p className="text-xs text-muted">
            Renaming onto a restaurant that already exists merges the two.
          </p>
          {error && <p className="text-sm text-accent-red">{error}</p>}
          <div className="flex gap-2">
            <button onClick={onClose}
              className="rounded-xl bg-surface-2 px-4 py-3 text-sm font-semibold text-foreground">
              Cancel
            </button>
            <button
              onClick={rename}
              disabled={busy || !name.trim()}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent-blue px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} Save
            </button>
          </div>
        </div>
      </ModalShell>
    );
  }

  const recipes = usage?.recipes || [];
  const needsSecond = recipes.length > 0;

  return (
    <ModalShell onClose={onClose} title={`Delete ${brand}?`}>
      <div className="flex flex-col gap-4">
        {!usage ? (
          <p className="flex items-center gap-2 py-4 text-sm text-muted">
            <Loader2 size={15} className="animate-spin" /> Checking what this affects…
          </p>
        ) : (
          <>
            <p className="text-sm text-foreground">
              This removes{" "}
              <span className="font-semibold">{usage.items} items</span> from your
              library. It cannot be undone.
            </p>

            {usage.logged_items > 0 && (
              <p className="rounded-xl bg-surface-2 p-3 text-xs text-muted">
                {usage.logged_items} of them appear in meals you’ve already logged.
                Those days keep their calories and macros — only the link back to
                the library is lost.
              </p>
            )}

            {needsSecond && (
              <div className="rounded-xl bg-red-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-accent-red">
                  <AlertTriangle size={13} />
                  {recipes.length === 1 ? "A recipe uses these items" : `${recipes.length} recipes use these items`}
                </p>
                <p className="mt-1 text-xs text-muted">
                  Deleting removes those ingredients from the {recipes.length === 1 ? "recipe" : "recipes"},
                  which changes {recipes.length === 1 ? "its" : "their"} totals:
                </p>
                <ul className="mt-1.5 flex flex-col gap-0.5">
                  {recipes.slice(0, 6).map(r => (
                    <li key={r} className="text-xs text-foreground">• {r}</li>
                  ))}
                  {recipes.length > 6 && (
                    <li className="text-xs text-muted">…and {recipes.length - 6} more</li>
                  )}
                </ul>
              </div>
            )}
          </>
        )}

        {error && <p className="text-sm text-accent-red">{error}</p>}

        <div className="flex gap-2">
          <button onClick={onClose}
            className="rounded-xl bg-surface-2 px-4 py-3 text-sm font-semibold text-foreground">
            Cancel
          </button>
          <button
            onClick={() => (needsSecond && !armed ? setArmed(true) : remove())}
            disabled={busy || !usage}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent-red px-4 py-3 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy
              ? <><Loader2 size={16} className="animate-spin" /> Deleting…</>
              : needsSecond && !armed
                ? <><AlertTriangle size={16} /> Delete anyway</>
                : <><Trash2 size={16} /> Delete {usage ? `${usage.items} items` : ""}</>}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
