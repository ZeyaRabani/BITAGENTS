"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { YieldAgentDeposit } from "@/components/agents/YieldAgentDeposit";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { useWallet } from "@solana/wallet-adapter-react";
import {
  fetchYieldDashboard,
  fetchYieldHealth,
  investYieldCapital,
  mapYieldActions,
  sendYieldAgentMessage,
  YIELD_EXAMPLE_PROMPTS,
  YIELD_TYPE_HELP,
  YIELD_TYPES,
  type YieldDashboard,
  type YieldHealth,
} from "@/lib/yieldAgentClient";
import type { AgentAction } from "@/lib/dcaAgentClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

export function YieldAgentConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();
  const [health, setHealth] = useState<YieldHealth | null>(null);
  const [dashboard, setDashboard] = useState<YieldDashboard | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [yieldType, setYieldType] = useState<(typeof YIELD_TYPES)[number]["id"]>("any");
  const [capital, setCapital] = useState("");
  const [durationDays, setDurationDays] = useState("30");
  const [investBusy, setInvestBusy] = useState(false);
  const [investNote, setInvestNote] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchYieldHealth().then(setHealth);
  }, []);

  useEffect(() => {
    if (!token) {
      setDashboard(null);
      return;
    }
    void fetchYieldDashboard(token).then(setDashboard);
  }, [token]);

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
      const res = await sendYieldAgentMessage(text.trim(), token, sessionId, history);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
      setActions(mapYieldActions(res.actions));
      const dash = await fetchYieldDashboard(token);
      if (dash) setDashboard(dash);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: "assistant", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  async function onTestKamino() {
    if (!token) return;
    setInvestBusy(true);
    setError(null);
    setInvestNote(null);
    try {
      const result = await investYieldCapital(token, {
        asset: "SOL",
        capital: 0.05,
        duration_days: 2,
        yield_type: "lending",
        skip_deposit_ledger: true,
        force_protocol: "kamino",
      });
      setInvestNote(result.message ?? "Kamino test deposit sent.");
      const dash = await fetchYieldDashboard(token);
      if (dash) setDashboard(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kamino test failed");
    } finally {
      setInvestBusy(false);
    }
  }

  async function onInvest(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    const amount = Number(capital);
    const days = Number(durationDays);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a capital amount greater than 0.");
      return;
    }
    if (!Number.isFinite(days) || days < 1) {
      setError("Duration must be at least 1 day.");
      return;
    }
    setInvestBusy(true);
    setError(null);
    setInvestNote(null);
    try {
      const result = await investYieldCapital(token, {
        asset: "SOL",
        capital: amount,
        duration_days: Math.round(days),
        yield_type: yieldType,
      });
      setInvestNote(result.message ?? "Requirements saved.");
      const dash = await fetchYieldDashboard(token);
      if (dash) setDashboard(dash);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invest failed");
    } finally {
      setInvestBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runCommand(text);
  }

  const online = health?.status === "ok";
  const venues = dashboard?.yields?.markets ?? dashboard?.yields?.executable_venues ?? [];
  const positions = dashboard?.positions ?? [];

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Send SOL to your Circle yield wallet. Pick a yield type and the agent ranks Kamino,
          Jupiter JLP, MarginFi, Drift, and Save. Kamino lending and vaults are deposited through
          the Kamino API. JLP is bought through Jupiter. Save is ranked from its API. MarginFi
          and Drift have no deposit API, so those winners stay idle. Not financial advice.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={`inline-flex items-center gap-2 ${online ? "text-signal" : "text-warn"}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${online ? "bg-signal animate-pulse-dot" : "bg-warn"}`} />
          {online ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? "hosted LLM"}</span>
        <span>·</span>
        <span className="text-signal">Free · wallet sign-in required</span>
      </div>

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
          Approve the wallet sign-in message to use the Yield Agent.
        </div>
      )}
      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to deposit capital and chat.
        </div>
      )}

      <YieldAgentDeposit cluster={health ? "mainnet" : undefined} authToken={token} />

      <Panel title="Requirements">
        <p className="text-sm text-muted-foreground">{YIELD_TYPE_HELP[yieldType]}</p>
        <form onSubmit={(e) => void onInvest(e)} className="mt-4 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Yield type
            <select
              value={yieldType}
              onChange={(e) =>
                setYieldType(e.target.value as (typeof YIELD_TYPES)[number]["id"])
              }
              disabled={investBusy}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50"
            >
              {YIELD_TYPES.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Capital
            <input
              type="number"
              min="0"
              step="0.01"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              placeholder="0.00"
              disabled={investBusy}
              className="w-32 border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Duration (days)
            <input
              type="number"
              min="1"
              step="1"
              value={durationDays}
              onChange={(e) => setDurationDays(e.target.value)}
              disabled={investBusy}
              className="w-28 border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground disabled:opacity-50"
            />
          </label>
          <button
            type="submit"
            disabled={!token || investBusy}
            className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
          >
            {investBusy ? "Comparing…" : "Find best and invest"}
          </button>
        </form>
        {investNote && <p className="mt-3 font-mono text-[11px] text-signal">{investNote}</p>}
        <div className="mt-4 border-t border-grid pt-4">
          <button
            type="button"
            disabled={!token || investBusy}
            onClick={() => void onTestKamino()}
            className="border border-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-signal transition hover:bg-signal/10 disabled:opacity-40"
          >
            {investBusy ? "Sending…" : "Test Kamino yield · 0.05 SOL"}
          </button>
          <p className="mt-2 text-sm text-muted-foreground">
            Uses 0.05 SOL already in the Circle wallet for 2 days of Kamino lending. This does not
            check a verified deposit.
          </p>
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Yield Agent" className="lg:col-span-2">
          <div className="flex max-h-105 flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Try a prompt below, or set capital, duration, and yield type, then invest.
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
                  {msg.role === "user" ? "You" : "Yield Agent"}
                </div>
                <div className="space-y-1">{formatReply(msg.content)}</div>
              </div>
            ))}
            {busy && (
              <div className="animate-pulse font-mono text-xs text-muted-foreground">Thinking…</div>
            )}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={isAuthenticated ? "Ask the yield agent…" : "Connect wallet and sign in"}
                disabled={!token || busy}
                className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!token || busy || !input.trim()}
                className="border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
        </Panel>

        <div className="space-y-6">
          <Panel title="Quick prompts">
            <div className="flex flex-col gap-2">
              {YIELD_EXAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={!token || busy}
                  onClick={() => void runCommand(prompt)}
                  className="border border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground transition hover:border-signal/40 hover:text-foreground disabled:opacity-40"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </Panel>

          <Panel title="Live venues">
            {venues.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sign in to load ranked APYs.</p>
            ) : (
              <div className="space-y-2">
                {venues.slice(0, 6).map((venue, index) => (
                  <div
                    key={`${venue.protocol_id ?? venue.symbol}-${venue.symbol}-${index}`}
                    className="flex items-baseline justify-between gap-2 border border-grid bg-surface/30 px-3 py-2"
                  >
                    <span className="font-mono text-xs text-foreground">
                      {venue.protocol_name ?? venue.symbol}
                      {venue.yield_type ? ` · ${venue.yield_type.split("_").join(" ")}` : ""}
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-signal">
                      {venue.apy != null ? `${venue.apy.toFixed(2)}%` : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Positions">
            {positions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No deployed yield yet.</p>
            ) : (
              <div className="space-y-2">
                {positions.map((pos) => (
                  <div key={pos.id} className="border border-grid bg-surface/30 px-3 py-2">
                    <div className="flex justify-between gap-2 font-mono text-xs">
                      <span>{pos.protocol_name}</span>
                      <span className="text-signal">
                        {pos.amount} {pos.symbol}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      Entry APY {pos.entry_apy != null ? `${pos.entry_apy.toFixed(2)}%` : "—"}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {actions.length > 0 && (
            <Panel title="Tool results">
              <div className="max-h-64 space-y-2 overflow-y-auto font-mono text-[11px]">
                {actions.map((action, idx) => (
                  <div key={`${action.tool}-${idx}`} className="border border-grid bg-surface/30 p-3">
                    <div className="mb-1 text-signal">{action.tool}</div>
                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                      {action.result}
                    </pre>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
