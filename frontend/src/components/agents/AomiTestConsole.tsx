"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel } from "@/components/AppShell";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { AOMI_TEST } from "@/lib/aomiTestConfig";
import {
  fetchAomiTestHealth,
  fetchAomiTestWallet,
  sendAomiTestMessage,
  sendAomiTestSol,
  type AomiTestHealth,
  type AomiTestSendResult,
  type AomiTestWallet,
} from "@/lib/aomiTestClient";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

export function AomiTestConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError } = useKickstartWalletAuth();
  const [health, setHealth] = useState<AomiTestHealth | null>(null);
  const [wallet, setWallet] = useState<AomiTestWallet | null>(null);
  const [destination, setDestination] = useState("");
  const [amount, setAmount] = useState("0.001");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AomiTestSendResult | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();

  const refreshWallet = useCallback(async () => {
    if (!token) {
      setWallet(null);
      return;
    }
    setWallet(await fetchAomiTestWallet(token));
  }, [token]);

  useEffect(() => {
    void fetchAomiTestHealth().then(setHealth);
  }, []);

  useEffect(() => {
    void refreshWallet().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Wallet lookup failed");
    });
  }, [refreshWallet]);

  async function onSend(e: FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("Connect your wallet and approve the sign-in message first.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const sent = await sendAomiTestSol(token, {
        destination: destination.trim(),
        amount_sol: Number(amount),
      });
      setResult(sent);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  async function onChat(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !token || busy) return;
    setInput("");
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text }]);
    try {
      const res = await sendAomiTestMessage(text, token, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", content: res.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Chat failed";
      setError(msg);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: "assistant", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  const maxSol = health?.max_send_sol ?? wallet?.max_send_sol ?? 0.05;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={health?.status === "ok" ? "text-signal" : "text-warn"}>
          {health?.status === "ok" ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span className={health?.aomi_configured ? "text-signal" : "text-warn"}>
          {health?.aomi_configured ? "Aomi token set" : "Aomi token missing"}
        </span>
        <span>·</span>
        <span className={health?.circle_configured ? "text-signal" : "text-warn"}>
          {health?.circle_configured ? "Circle ready" : "Circle missing"}
        </span>
        <span>·</span>
        <span>{health?.cluster ?? "cluster"}</span>
      </div>

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{authError}</div>
      )}
      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to create the Test Aomi Circle address.
        </div>
      )}
      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message.
        </div>
      )}

      <Panel title="Circle agent wallet">
        <p className="text-sm text-muted-foreground">
          Fund this address with a little SOL. Aomi builds the transfer. Circle signs it from this address.
        </p>
        <p className="mt-3 break-all font-mono text-sm text-foreground">
          {wallet?.agent_wallet || (token ? "Creating wallet…" : "Sign in to create the agent wallet")}
        </p>
        {wallet?.error && <p className="mt-2 font-mono text-xs text-warn">{wallet.error}</p>}
      </Panel>

      <Panel title="Send SOL">
        <form onSubmit={(e) => void onSend(e)} className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:col-span-2">
            Destination
            <input
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder="Solana address"
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Amount (max {maxSol} SOL)
            <input
              type="number"
              min="0.000001"
              max={maxSol}
              step="0.000001"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={!token || busy}
              className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
            >
              {busy ? "Working…" : "Send via Aomi + Circle"}
            </button>
          </div>
        </form>
        {result?.signature && (
          <p className="mt-3 break-all font-mono text-xs text-signal">
            {result.signature}
            {result.explorer_url ? ` · ${result.explorer_url}` : ""}
          </p>
        )}
      </Panel>

      <Panel title={`Chat · ${AOMI_TEST.name}`}>
        <div className="flex max-h-[320px] flex-col gap-3 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Try: Send 0.001 SOL to a destination address. Other messages go to the Aomi agent, and any
              unsigned SOL transfer is signed by this Circle wallet.
            </p>
          )}
          {messages.map((msg) => (
            <div key={msg.id} className="border border-grid px-3 py-2 text-sm">
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-signal">
                {msg.role === "user" ? "You" : AOMI_TEST.assistantLabel}
              </div>
              <p className="whitespace-pre-wrap text-muted-foreground">{msg.content}</p>
            </div>
          ))}
        </div>
        <form onSubmit={(e) => void onChat(e)} className="mt-4 flex gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={!token || busy}
            placeholder="Send 0.001 SOL to …"
            className="flex-1 border border-grid bg-background px-4 py-3 font-mono text-sm text-foreground outline-none focus:border-signal disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!token || busy || !input.trim()}
            className="bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </Panel>
    </div>
  );
}
