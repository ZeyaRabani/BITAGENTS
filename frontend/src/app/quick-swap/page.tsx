"use client";

import { FormEvent, useState } from "react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";

type Preview = {
  confirm_text: string;
  input_token: string;
  output_token: string;
  amount: number;
};

type ExecuteResult = {
  status: string;
  signature?: string;
  explorer_url?: string;
  output_amount?: number;
  error?: string;
};

export default function QuickSwapPage() {
  const { token, isAuthenticated, busy: authBusy, error: authError } = useDcaWalletAuth();
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ExecuteResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handlePreview(e: FormEvent) {
    e.preventDefault();
    if (!token || !message.trim()) return;
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await fetch("/api/agents/quick-swap/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Preview failed");
      setPreview(data as Preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    if (!token) return;
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/agents/quick-swap/execute", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Swap failed");
      setResult(data as ExecuteResult);
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Swap failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-xl px-4 py-12">
      <p className="text-sm font-black uppercase text-ember">Quick Swap MVP</p>
      <h1 className="mt-2 text-3xl font-black text-white">
        One sentence in, one real on-chain swap out
      </h1>
      <p className="mt-3 text-slate-300">
        Fixed for this demo: 0.005 SOL (~$1) → BITAGENTS. Describe wanting the swap in your own
        words — the agent confirms the exact action before anything executes on-chain.
      </p>

      <div className="mt-6">
        <WalletMultiButton />
        {authBusy && <p className="mt-2 text-sm text-slate-400">Signing in…</p>}
        {authError && <p className="mt-2 text-sm text-red-400">{authError}</p>}
      </div>

      {isAuthenticated && (
        <form onSubmit={handlePreview} className="mt-6 flex flex-col gap-3">
          <input
            className="rounded-md border border-line bg-ink/70 px-4 py-3 text-white outline-none focus:border-ember"
            placeholder='e.g. "swap some SOL for BITAGENTS"'
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !message.trim()}
            className="rounded-md bg-ember px-4 py-3 font-black text-ink transition hover:bg-coral disabled:opacity-45"
          >
            {loading ? "Thinking…" : "Ask the agent"}
          </button>
        </form>
      )}

      {error && (
        <p className="mt-4 rounded-md border border-red-400/50 bg-red-400/10 p-3 text-sm font-bold text-red-300">
          {error}
        </p>
      )}

      {preview && (
        <div className="mt-6 rounded-md border border-line bg-panel/80 p-5">
          <p className="text-white">{preview.confirm_text}</p>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="mt-4 rounded-md bg-ember px-4 py-3 font-black text-ink transition hover:bg-coral disabled:opacity-45"
          >
            {loading ? "Executing…" : "Confirm & Swap"}
          </button>
        </div>
      )}

      {result && (
        <div className="mt-6 rounded-md border border-line bg-panel/80 p-5">
          {result.status === "error" || result.error ? (
            <p className="text-red-300">{result.error}</p>
          ) : (
            <>
              <p className="text-white">
                Swap complete. Received {result.output_amount ?? "?"} BITAGENTS.
              </p>
              {result.explorer_url && (
                <a
                  href={result.explorer_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block font-black text-skybit hover:text-white"
                >
                  View transaction on Solana Explorer →
                </a>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
