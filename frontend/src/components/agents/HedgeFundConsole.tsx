"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import {
  fetchHedgeFundHealth,
  mapHedgeFundActions,
  sendHedgeFundMessage,
  type HedgeFundHealth,
} from "@/lib/hedgeFundClient";
import { HEDGE_FUND } from "@/lib/hedgeFundConfig";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { useWallet } from "@solana/wallet-adapter-react";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

export function HedgeFundConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();
  const [health, setHealth] = useState<HedgeFundHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchHedgeFundHealth().then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
    });
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function runCommand(text: string) {
    if (!token || !text.trim()) return;
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text.trim() }]);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await sendHedgeFundMessage(text.trim(), token, sessionId, history);
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", content: res.reply }]);
      setActions(mapHedgeFundActions(res.actions));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: "assistant", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runCommand(text);
  }

  return (
    <div className="space-y-6">
      <div className="border-2 border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">{HEDGE_FUND.description}</p>
        <p className="mt-2 font-mono text-xs text-signal">
          Fee model: {HEDGE_FUND.managementFeePct}% management + {HEDGE_FUND.performanceFeePct}% performance ·{" "}
          <Link href="/agents/hedge-fund/pricing" className="underline hover:text-foreground">
            View pricing
          </Link>
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={`inline-flex items-center gap-2 ${agentOnline ? "text-signal" : "text-warn"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${agentOnline ? "bg-signal animate-pulse-dot" : "bg-warn"}`} />
          {agentOnline ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? HEDGE_FUND.model}</span>
        <span>·</span>
        <span className="text-signal">1/10 fee model</span>
      </div>

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={HEDGE_FUND.name} className="lg:col-span-2">
          <div className="flex max-h-[480px] flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Ask for a portfolio analysis on Solana tokens. Quant/value analysts run deterministically; macro
                synthesis uses the hosted LLM.
              </p>
            )}
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
                  {msg.role === "user" ? "You" : HEDGE_FUND.assistantLabel}
                </div>
                <div className="space-y-1">{formatReply(msg.content)}</div>
              </div>
            ))}
            {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Analyzing portfolio…</div>}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 border-t-2 border-grid pt-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={isAuthenticated ? "e.g. Analyze SOL JUP BITAGENTS with $10,000" : "Connect wallet to chat"}
                disabled={!token || busy}
                className="flex-1 border-2 border-grid bg-background px-3 py-2 font-mono text-sm disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!token || busy || !input.trim()}
                className="border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase text-signal disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
        </Panel>

        <div className="space-y-6">
          <Panel title="Quick prompts">
            <div className="flex flex-col gap-2">
              {HEDGE_FUND.examplePrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={!token || busy}
                  onClick={() => void runCommand(prompt)}
                  className="border-2 border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground hover:border-signal/40 disabled:opacity-40"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </Panel>

          {actions.length > 0 && (
            <Panel title="Analyst signals">
              <div className="max-h-80 space-y-3 overflow-y-auto font-mono text-[11px]">
                {actions.map((action, idx) => (
                  <div key={`${action.tool}-${idx}`} className="border-2 border-grid bg-surface/30 p-3">
                    <div className="mb-1 text-signal">{action.tool}</div>
                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">{action.result}</pre>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>

      {!publicKey && (
        <div className="border-2 border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in.
        </div>
      )}
    </div>
  );
}
