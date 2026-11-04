"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel } from "@/components/AppShell";
import { InstructionsDialog } from "@/components/agents/InstructionsDialog";
import { JupiterTradeDeposit } from "@/components/agents/JupiterTradeDeposit";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { getCustomInstructions, saveCustomInstructions } from "@/lib/customInstructionsClient";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { JUPITER_TRADE } from "@/lib/jupiterTradeConfig";
import {
  closeJupiterTradeStrategy,
  confirmJupiterTradeLive,
  confirmJupiterTradeUnderstanding,
  createJupiterTradeStrategy,
  fetchJupiterTradeDashboard,
  fetchJupiterTradeHealth,
  fetchJupiterTradeTemplates,
  mapJupiterTradeActions,
  runJupiterTradeMonitor,
  sendJupiterTradeMessage,
  type JupiterTradeDashboard,
  type JupiterTradeHealth,
  type JupiterTradeStrategy,
  type JupiterTradeTemplate,
} from "@/lib/jupiterTradeClient";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

export function JupiterTradeConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();

  const [health, setHealth] = useState<JupiterTradeHealth | null>(null);
  const [dashboard, setDashboard] = useState<JupiterTradeDashboard | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [dashBusy, setDashBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [symbols, setSymbols] = useState("BONK JUP");
  const [capitalSol, setCapitalSol] = useState("1");
  const [tp, setTp] = useState("12");
  const [sl, setSl] = useState("6");
  const [notes, setNotes] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [templates, setTemplates] = useState<JupiterTradeTemplate[]>([]);
  const [templateFamilies, setTemplateFamilies] = useState<string[]>([]);
  const [templateFamily, setTemplateFamily] = useState("");
  const [templateQuery, setTemplateQuery] = useState("");
  const [templateTotal, setTemplateTotal] = useState(0);

  const [customInstructions, setCustomInstructions] = useState("");
  const [instructionsOpen, setInstructionsOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);

  const refreshDashboard = useCallback(async () => {
    if (!token) {
      setDashboard(null);
      return;
    }
    setDashboard(await fetchJupiterTradeDashboard(token));
  }, [token]);

  useEffect(() => {
    void fetchJupiterTradeHealth().then(setHealth);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void fetchJupiterTradeTemplates({
      family: templateFamily || undefined,
      query: templateQuery || undefined,
      limit: 150,
    })
      .then((res) => {
        if (cancelled) return;
        setTemplates(res.templates ?? []);
        setTemplateFamilies(res.families ?? []);
        setTemplateTotal(res.total_catalog ?? res.count ?? 0);
      })
      .catch(() => {
        if (!cancelled) {
          setTemplates([]);
          setTemplateFamilies([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [templateFamily, templateQuery]);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  useEffect(() => {
    if (!token) return;
    void getCustomInstructions("jupiter_trade", token)
      .then(setCustomInstructions)
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function runCommand(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    if (!token) {
      setError("Connect your wallet and approve the sign-in message first.");
      return;
    }
    setInput("");
    setBusy(true);
    setError(null);
    const messageWithInstructions = customInstructions.trim()
      ? `[Custom Instructions: ${customInstructions.trim()}]\n\n${trimmed}`
      : trimmed;
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await sendJupiterTradeMessage(
        messageWithInstructions,
        token,
        sessionId,
        history
      );
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
      setActions(mapJupiterTradeActions(res.actions));
      await refreshDashboard();
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
    void runCommand(input);
  }

  async function onPropose(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setDashBusy(true);
    setError(null);
    try {
      const result = await createJupiterTradeStrategy(token, {
        symbols,
        capital_sol: Number(capitalSol) || 1,
        take_profit_pct: Number(tp) || 12,
        stop_loss_pct: Number(sl) || 6,
        notes,
        template_id: templateId || undefined,
      });
      const understanding =
        (result.understanding as string) ||
        ((result.strategy as JupiterTradeStrategy | undefined)?.understanding ?? "");
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: understanding || "Strategy proposed. Confirm understanding to start paper.",
        },
      ]);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Propose failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onConfirmUnderstanding(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    setError(null);
    try {
      await confirmJupiterTradeUnderstanding(token, strategyId);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onConfirmLive(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    setError(null);
    try {
      await confirmJupiterTradeLive(token, strategyId);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Live confirm failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onClose(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      await closeJupiterTradeStrategy(token, strategyId);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Close failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onMonitor() {
    if (!token) return;
    setDashBusy(true);
    try {
      await runJupiterTradeMonitor(token);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Monitor failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onSaveInstructions(instructions: string) {
    if (!token) return;
    await saveCustomInstructions("jupiter_trade", instructions, token);
    setCustomInstructions(instructions);
    setInstructionsOpen(false);
  }

  const online = health?.status === "ok" || health?.status === "degraded";
  const paperMin = dashboard?.paper_min_hours ?? health?.paper_min_hours ?? 24;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={`inline-flex items-center gap-2 ${online ? "text-signal" : "text-warn"}`}>
          <span
            className={`h-1.5 w-1.5 rounded-full ${online ? "bg-signal animate-pulse-dot" : "bg-warn"}`}
          />
          {online ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? JUPITER_TRADE.model}</span>
        <span>·</span>
        <span className="text-signal">Jupiter spot · Circle wallet</span>
        <span>·</span>
        <span>0.1% / live trade</span>
        <span>·</span>
        <span>Paper ≥ {paperMin}h</span>
        <span>·</span>
        <span>{(health?.strategy_templates ?? templateTotal) || "100+"} templates</span>
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
          Approve the wallet sign-in message to authenticate.
        </div>
      )}
      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to propose strategies and chat.
        </div>
      )}
      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to use {JUPITER_TRADE.name}.
        </div>
      )}

      <Panel title="Propose strategy · Jupiter spot">
        <form onSubmit={(e) => void onPropose(e)} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Family
            <select
              value={templateFamily}
              onChange={(e) => setTemplateFamily(e.target.value)}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            >
              <option value="">All families</option>
              {templateFamilies.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground lg:col-span-2">
            Search algos
            <input
              value={templateQuery}
              onChange={(e) => setTemplateQuery(e.target.value)}
              placeholder="MACD, RSI, Supertrend…"
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:col-span-2 lg:col-span-2">
            Strategy template ({templateTotal || templates.length})
            <select
              value={templateId}
              onChange={(e) => {
                const id = e.target.value;
                setTemplateId(id);
                const picked = templates.find((t) => t.id === id);
                if (picked?.default_tp_pct && picked.default_tp_pct > 0) {
                  setTp(String(picked.default_tp_pct));
                }
                if (picked?.default_sl_pct && picked.default_sl_pct > 0) {
                  setSl(String(picked.default_sl_pct));
                }
              }}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            >
              <option value="">Custom / notes only</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} · {t.family}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground lg:col-span-2">
            Tokens
            <input
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="BONK JUP"
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Capital (SOL)
            <input
              type="number"
              min="0.05"
              step="0.01"
              value={capitalSol}
              onChange={(e) => setCapitalSol(e.target.value)}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            TP %
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={tp}
              onChange={(e) => setTp(e.target.value)}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            SL %
            <input
              type="number"
              min="0.1"
              step="0.1"
              value={sl}
              onChange={(e) => setSl(e.target.value)}
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground sm:col-span-2 lg:col-span-4">
            Notes / how you want to trade
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Equal weight, hold until TP/SL…"
              className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!token || dashBusy}
              className="w-full bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
            >
              {dashBusy ? "Proposing…" : "Propose & restate"}
            </button>
          </div>
        </form>
        {templateId && (
          <p className="mt-3 font-mono text-[11px] text-muted-foreground">
            {templates.find((t) => t.id === templateId)?.summary ?? templateId}
          </p>
        )}
      </Panel>

      <JupiterTradeDeposit cluster={health?.cluster ?? JUPITER_TRADE.cluster} authToken={token} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title={`Command ${JUPITER_TRADE.name}`}
          className="lg:col-span-2"
          action={
            <button
              type="button"
              onClick={() => setInstructionsOpen(true)}
              className="rounded border border-grid bg-surface px-3 py-1.5 text-xs font-medium uppercase tracking-wider transition hover:border-signal hover:text-signal"
            >
              Instructions
            </button>
          }
        >
          <div className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Flow: propose → confirm understanding → ≥{paperMin}h paper → confirm live. Jupiter
                Perps are disabled.
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
                  {msg.role === "user" ? "You" : JUPITER_TRADE.assistantLabel}
                </div>
                <div className="space-y-1">{formatReply(msg.content)}</div>
              </div>
            ))}
            {busy && (
              <div className="animate-pulse font-mono text-xs text-muted-foreground">
                Working… (AI Agent may take a moment)
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy || !token}
                placeholder={token ? "e.g. Confirm understanding jt…" : "Sign in with wallet to chat"}
                className="flex-1 border border-grid bg-background px-4 py-3 font-mono text-sm text-foreground outline-none focus:border-signal disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={busy || !input.trim() || !token}
                className="bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
          <div className="mt-4 flex flex-wrap gap-2">
            {JUPITER_TRADE.examplePrompts.map((prompt) => (
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
              <p className="text-muted-foreground">
                Tool calls appear here - propose, confirm, paper gate, live deploy.
              </p>
            )}
            {actions.map((act, index) => (
              <div key={`${act.tool}-${index}`} className="border border-grid bg-surface/30 p-3">
                <div className="mb-1 text-signal">
                  {index + 1}. {act.tool}
                </div>
                <pre className="whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
                  {act.result || act.error || JSON.stringify(act.args ?? {}, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel
        title="Strategies · paper gate"
        action={
          <button
            type="button"
            disabled={!token || dashBusy}
            onClick={() => void onMonitor()}
            className="border border-grid px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground disabled:opacity-40"
          >
            Run monitor
          </button>
        }
      >
        {!dashboard?.strategies?.length ? (
          <p className="text-sm text-muted-foreground">No strategies yet.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {dashboard.strategies.map((strategy) => {
              const gate = strategy.gate;
              const canLive = Boolean(gate?.ready_for_live_confirm);
              return (
                <div key={strategy.id} className="border border-grid bg-surface/30 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-display text-base font-bold">{strategy.name}</div>
                      <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
                        {strategy.status}
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-muted-foreground">
                        {strategy.id} · {(strategy.symbols || []).join(", ")}
                        {strategy.rules?.template_name
                          ? ` · ${strategy.rules.template_name}`
                          : ""}
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled={dashBusy}
                      onClick={() => void onClose(strategy.id)}
                      className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-warn hover:text-warn"
                    >
                      Close
                    </button>
                  </div>

                  {strategy.understanding && (
                    <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                      {strategy.understanding}
                    </p>
                  )}

                  {gate && (
                    <div className="mt-3 grid grid-cols-3 gap-2 border-t border-grid pt-3 font-mono text-[11px]">
                      <div>
                        <div className="text-muted-foreground">Elapsed</div>
                        <div>{gate.hours_elapsed}h</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Remaining</div>
                        <div>{gate.hours_remaining}h</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Live gate</div>
                        <div className={canLive ? "text-signal" : ""}>
                          {canLive ? "ready" : "locked"}
                        </div>
                      </div>
                    </div>
                  )}

                  {(strategy.recent_trades || []).length > 0 && (
                    <div className="mt-3 space-y-1 border-t border-grid pt-3 font-mono text-[11px]">
                      {(strategy.recent_trades || []).slice(0, 4).map((trade) => (
                        <div key={trade.id || `${trade.symbol}-${trade.created_at}`}>
                          {trade.mode} {trade.side} {trade.symbol} @ {trade.price_usd?.toFixed?.(4) ?? "—"}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {strategy.status === "awaiting_confirm" && (
                      <button
                        type="button"
                        disabled={dashBusy}
                        onClick={() => void onConfirmUnderstanding(strategy.id)}
                        className="bg-signal px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
                      >
                        Confirm understanding
                      </button>
                    )}
                    {(strategy.status === "paper_ready" ||
                      (strategy.status === "paper_running" && canLive)) && (
                      <button
                        type="button"
                        disabled={dashBusy || !canLive}
                        onClick={() => void onConfirmLive(strategy.id)}
                        className="border border-signal px-3 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-signal disabled:opacity-40"
                      >
                        Confirm live
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <InstructionsDialog
        open={instructionsOpen}
        onOpenChange={setInstructionsOpen}
        instructions={customInstructions}
        onSave={onSaveInstructions}
      />
      <LegalSignInNotice />
    </div>
  );
}
