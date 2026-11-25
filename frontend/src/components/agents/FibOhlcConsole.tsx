"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { useWallet } from "@solana/wallet-adapter-react";
import { fibOhlcApi } from "@/lib/fibOhlcClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type ActionRow = {
  id: string;
  tool: string;
  result: string;
};

const PROMPTS = [
  "Show Fib setup for BTC",
  "Run paper trade on BTC",
  "Backtest BTC 90 days",
  "Show my paper book",
  "Show Fib setup for ETH",
];

export function FibOhlcConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "intro",
      role: "assistant",
      content:
        "Connected to the Fibonacci OHLC agent (paper only). Ask for a setup, run a paper trade, or backtest. Default asset is BTC. Risk:reward is 1:3.",
    },
  ]);
  const [actions, setActions] = useState<ActionRow[]>([]);
  const [book, setBook] = useState<{
    cash_usd: number;
    realized_pnl_usd: number;
    open: unknown;
    trades: unknown[];
  } | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!token) {
      setBook(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const data = await fibOhlcApi.book(token);
        if (!cancelled) setBook(data);
      } catch {
        if (!cancelled) setBook(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, actions.length]);

  async function runCommand(command: string) {
    const text = command.trim();
    if (!text || !token) return;
    setBusy(true);
    setError(null);
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: "user", content: text }]);
    try {
      const res = await fetch("/api/agents/fib-ohlc/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const data = (await res.json()) as {
        reply?: string;
        session_id?: string;
        actions?: { tool: string; args: Record<string, unknown>; result: string }[];
        detail?: string;
        error?: string;
      };
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Request failed");
      }
      if (data.session_id) setSessionId(data.session_id);
      const nextActions = (data.actions ?? []).map((item, index) => ({
        id: `${Date.now()}-${index}`,
        tool: item.tool,
        result: item.result,
      }));
      setActions((current) => [...current, ...nextActions]);
      setMessages((current) => [
        ...current,
        { id: `agent-${Date.now()}`, role: "assistant", content: data.reply || "No reply." },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
      setInput("");
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void runCommand(input);
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}
      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to authenticate.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Command Fibonacci OHLC" className="lg:col-span-2">
          <div className="mb-3 inline-flex border border-signal/50 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
            Paper mode
          </div>
          <div className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`rounded border px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "border-grid bg-surface/60 text-foreground"
                    : "border-signal/30 bg-surface/30 text-muted-foreground"
                }`}
              >
                <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                  {msg.role === "user" ? "You" : "Agent"}
                </div>
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            ))}
            {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Working…</div>}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={busy || !token}
                placeholder={token ? "Ask for a Fib setup or paper trade" : "Sign in with wallet to chat"}
                className="flex-1 border border-grid bg-background px-4 py-3 font-mono text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-signal disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={busy || !input.trim() || !token}
                className="bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
          <div className="mt-4 flex flex-wrap gap-2">
            {PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={busy || !token}
                onClick={() => void runCommand(prompt)}
                className="border border-grid px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground transition hover:border-signal hover:text-foreground disabled:opacity-40"
              >
                {prompt}
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Agent action">
          <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1 font-mono text-xs">
            {actions.length === 0 && (
              <p className="text-muted-foreground">Inspect, paper fills, and backtest summaries show up here.</p>
            )}
            {actions.map((act) => (
              <div key={act.id} className="border border-grid px-3 py-2">
                <div className="uppercase tracking-[0.14em] text-signal">done {act.tool}</div>
                <p className="mt-1 break-words text-muted-foreground">{act.result}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="Paper book">
        {!isAuthenticated && (
          <p className="font-mono text-xs text-muted-foreground">
            Sign in with your wallet to run paper Fib trades and keep a session book.
          </p>
        )}
        {isAuthenticated && !book && (
          <p className="font-mono text-xs text-muted-foreground">Loading paper book…</p>
        )}
        {book && (
          <div className="grid gap-4 font-mono text-xs sm:grid-cols-3">
            <div>
              <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Cash</div>
              <div className="mt-1 text-foreground">${book.cash_usd}</div>
            </div>
            <div>
              <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Realized PnL</div>
              <div className="mt-1 text-foreground">${book.realized_pnl_usd}</div>
            </div>
            <div>
              <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Trades</div>
              <div className="mt-1 text-foreground">{book.trades?.length ?? 0}</div>
            </div>
            <p className="sm:col-span-3 text-muted-foreground">
              Paper mode only. Daily Fib 61.8% entries with 1:3 risk reward. No live orders.
            </p>
          </div>
        )}
      </Panel>

      <LegalSignInNotice />
    </div>
  );
}
