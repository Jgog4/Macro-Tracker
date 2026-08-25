/** My Account — set or change the app password. */
import { useState, useEffect } from "react";
import { Loader2, Check, ShieldCheck, ShieldAlert } from "lucide-react";
import { authApi, setToken } from "../api/client";
import { ModalShell } from "./AddFoodModal";

const MIN_LEN = 8;

export default function AccountModal({ onClose }) {
  const [hasPassword, setHasPassword] = useState(null);   // null = loading
  const [current, setCurrent] = useState("");
  const [next, setNext]       = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving]   = useState(false);
  const [error, setError]     = useState("");
  const [done, setDone]       = useState(false);

  useEffect(() => {
    authApi.status()
      .then((r) => setHasPassword(r.data.password_is_set))
      .catch(() => setHasPassword(false));
  }, []);

  const tooShort = next.length > 0 && next.length < MIN_LEN;
  const mismatch = confirm.length > 0 && next !== confirm;
  const canSave  = next.length >= MIN_LEN && next === confirm && !saving;

  const save = async (e) => {
    e?.preventDefault();
    if (!canSave) return;
    setSaving(true); setError("");
    try {
      const res = await authApi.setPassword(next, current);
      // Password change rotates the token — keep this device signed in.
      if (res.data.token) setToken(res.data.token);
      setDone(true);
      setCurrent(""); setNext(""); setConfirm("");
      setHasPassword(true);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
        (!err.response ? "Network error — check your connection." : "Couldn't update the password.")
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell onClose={onClose} title="My Account">
      <div className="flex flex-col gap-4">

        {/* Current protection state */}
        {hasPassword === null ? (
          <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-muted" /></div>
        ) : hasPassword ? (
          <div className="flex items-start gap-2.5 bg-green-50 rounded-xl px-3 py-2.5">
            <ShieldCheck size={16} className="text-accent-green shrink-0 mt-0.5" />
            <p className="text-[11px] text-foreground">
              Your account is password protected.
            </p>
          </div>
        ) : (
          <div className="flex items-start gap-2.5 bg-amber-50 rounded-xl px-3 py-2.5">
            <ShieldAlert size={16} className="text-accent-orange shrink-0 mt-0.5" />
            <p className="text-[11px] text-foreground">
              No app password set yet. Setting one here replaces the server
              configuration and protects all your data.
            </p>
          </div>
        )}

        {done && (
          <div className="flex items-start gap-2.5 bg-green-50 rounded-xl px-3 py-2.5">
            <Check size={16} className="text-accent-green shrink-0 mt-0.5" />
            <p className="text-[11px] text-foreground">
              Password updated. Other devices have been signed out.
            </p>
          </div>
        )}

        {hasPassword !== null && (
          <form onSubmit={save} className="flex flex-col gap-3">
            {hasPassword && (
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                  Current password
                </label>
                <input type="password" value={current} autoComplete="current-password"
                       onChange={(e) => setCurrent(e.target.value)} className="input" />
                <p className="text-[10px] text-muted">
                  Not needed while you're already signed in on this device.
                </p>
              </div>
            )}

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                New password
              </label>
              <input type="password" value={next} autoComplete="new-password"
                     onChange={(e) => setNext(e.target.value)} className="input" />
              {tooShort && <p className="text-[11px] text-accent-red">At least {MIN_LEN} characters.</p>}
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                Confirm new password
              </label>
              <input type="password" value={confirm} autoComplete="new-password"
                     onChange={(e) => setConfirm(e.target.value)} className="input" />
              {mismatch && <p className="text-[11px] text-accent-red">Passwords don't match.</p>}
            </div>

            {error && <p className="text-accent-red text-xs">{error}</p>}

            <button type="submit" disabled={!canSave}
                    className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40">
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
              {hasPassword ? "Change Password" : "Set Password"}
            </button>
          </form>
        )}

        <p className="text-[10px] text-muted text-center">
          Stored as a salted PBKDF2 hash — never in plain text.
          Changing it signs out every other device.
        </p>
      </div>
    </ModalShell>
  );
}
