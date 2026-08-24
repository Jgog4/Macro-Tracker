/** Password gate shown when the app is locked. */
import { useState } from "react";
import { Lock, Loader2 } from "lucide-react";
import { authApi, setToken } from "../api/client";

export default function LoginScreen({ onSuccess }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState("");

  const submit = async (e) => {
    e?.preventDefault();
    if (!password) return;
    setBusy(true); setError("");
    try {
      const res = await authApi.login(password);
      setToken(res.data.token);
      onSuccess();
    } catch (err) {
      setError(
        err.response?.status === 401
          ? "Incorrect password."
          : !err.response ? "Network error — check your connection."
          : "Something went wrong. Try again."
      );
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen w-full max-w-md mx-auto bg-surface flex flex-col items-center justify-center px-6 gap-6">
      <div className="w-14 h-14 rounded-2xl bg-accent-blue flex items-center justify-center">
        <span className="text-white text-xl font-bold">M</span>
      </div>
      <div className="text-center">
        <h1 className="text-xl font-bold text-foreground">Macro Tracker</h1>
        <p className="text-sm text-muted mt-1">Enter your password to continue</p>
      </div>

      <form onSubmit={submit} className="w-full flex flex-col gap-3">
        <div className="relative">
          <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            autoFocus
            autoComplete="current-password"
            className="input pl-9"
          />
        </div>
        {error && <p className="text-accent-red text-xs text-center">{error}</p>}
        <button
          type="submit"
          disabled={busy || !password}
          className="btn-primary w-full flex items-center justify-center gap-2 py-3.5 disabled:opacity-40"
        >
          {busy && <Loader2 size={15} className="animate-spin" />}
          Sign In
        </button>
      </form>

      <p className="text-[11px] text-muted text-center">
        You'll stay signed in on this device.
      </p>
    </div>
  );
}
