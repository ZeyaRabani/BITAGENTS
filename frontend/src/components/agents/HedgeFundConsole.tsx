"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { HedgeFundDeposit } from "@/components/agents/HedgeFundDeposit";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  addPaperStrategyCapital,
  analyzePaperAsset,
  dismissPaperStrategy,
  fetchHedgeFundHealth,
  fetchPaperDashboard,
  fetchStrategyLivePnl,
  liquidatePaperStrategy,
  mapHedgeFundActions,
  retryPaperStrategy,
  runPaperBacktest,
  runPaperMonitor,
  sendHedgeFundMessage,
  updatePaperStrategy,
  type HedgeFundHealth,
  type PaperDashboard,
} from "@/lib/hedgeFundClient";
import { HEDGE_FUND } from "@/lib/hedgeFundConfig";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { useWallet } from "@solana/wallet-adapter-react";
import type { HfUserDepositBalances } from "@/lib/hedgeFundWalletClient";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

function money(n?: number | null) {
  if (n == null || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs === 0) return "$0.00";
  if (abs >= 0.01) {
    return `$${n.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  // Preserve two significant digits for tiny values: 0.000567 → 0.00057.
  return `$${Number(n.toPrecision(2)).toString()}`;
}

function preciseNumber(n?: number | null, suffix = "") {
  if (n == null || Number.isNaN(n)) return `—${suffix}`;
  const abs = Math.abs(n);
  if (abs === 0) return `0.00${suffix}`;
  if (abs >= 0.01) return `${n.toFixed(2)}${suffix}`;
  return `${Number(n.toPrecision(2)).toString()}${suffix}`;
}

type TxRow = {
  signature?: string | null;
  explorer_url?: string | null;
  symbol?: string;
  side?: string;
};

function CloseTxLinks({
  txs,
  trades,
  swapped,
}: {
  txs?: TxRow[];
  trades?: TxRow[];
  swapped?: boolean;
}) {
  const rows: { sig: string; href: string; label: string }[] = [];
  const seen = new Set<string>();
  const add = (t: TxRow, allSides: boolean) => {
    const sig = t.signature ? String(t.signature) : "";
    if (!sig || seen.has(sig)) return;
    const side = String(t.side || "").toUpperCase();
    if (!allSides && side && side !== "SELL" && side !== "FEE") return;
    seen.add(sig);
    rows.push({
      sig,
      href: t.explorer_url || explorerUrlForSignature(sig, HEDGE_FUND.cluster),
      label: `${t.side || "tx"} ${t.symbol || ""}`.trim(),
    });
  };
  for (const t of txs || []) add(t, true);
  for (const t of trades || []) add(t, false);
  if (rows.length === 0 && !swapped) return null;
  return (
    <div className="mt-2 space-y-1">
      {swapped && <div className="text-signal">Swapped back to SOL</div>}
      {rows.length > 0 && <div className="text-muted-foreground">Close / swap tx</div>}
      {rows.map((r) => (
        <a
          key={r.sig}
          href={r.href}
          target="_blank"
          rel="noopener noreferrer"
          className="block break-all text-[10px] text-signal hover:underline"
          title={r.sig}
        >
          {r.label} · {r.sig.slice(0, 12)}…{r.sig.slice(-8)} ↗
        </a>
      ))}
    </div>
  );
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
  const [dashboard, setDashboard] = useState<PaperDashboard | null>(null);
  const [dashBusy, setDashBusy] = useState(false);
  const [editTp, setEditTp] = useState<Record<string, string>>({});
  const [editSl, setEditSl] = useState<Record<string, string>>({});
  const [editHorizon, setEditHorizon] = useState<Record<string, string>>({});
  const [editAddCap, setEditAddCap] = useState<Record<string, string>>({});
  const [depositTick, setDepositTick] = useState(0);
  const [hfBalances, setHfBalances] = useState<HfUserDepositBalances | null>(null);
  const [strategyBacktests, setStrategyBacktests] = useState<Record<string, string>>({});
  const [strategyLivePnl, setStrategyLivePnl] = useState<Record<string, string>>({});
  const [lastAnalysis, setLastAnalysis] = useState<string | null>(null);
  const [lastRetryMsg, setLastRetryMsg] = useState<string | null>(null);
  const [liquidateStrategyId, setLiquidateStrategyId] = useState<string | null>(null);
  const [liquidateBusy, setLiquidateBusy] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const refreshDashboard = useCallback(async () => {
    if (!token) return;
    setDashBusy(true);
    try {
      const dash = await fetchPaperDashboard(token);
      setDashboard(dash);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load paper dashboard");
    } finally {
      setDashBusy(false);
    }
  }, [token]);

  useEffect(() => {
    void fetchHedgeFundHealth().then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
    });
  }, []);

  useEffect(() => {
    if (token) void refreshDashboard();
  }, [token, refreshDashboard]);

  useEffect(() => {
    if (!token) return;
    const interval = window.setInterval(() => {
      void refreshDashboard();
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [token, refreshDashboard]);

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
      void refreshDashboard();
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

  async function onSaveRules(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      const hzRaw = (editHorizon[strategyId] ?? "").trim();
      const horizon =
        hzRaw === ""
          ? undefined
          : hzRaw === "0" || hzRaw.toLowerCase() === "open"
            ? 0
            : Math.max(health?.min_horizon_days ?? 3, Number(hzRaw) || 0);
      const addCap = Number(editAddCap[strategyId] || 0);
      await updatePaperStrategy(token, strategyId, {
        take_profit_pct: Number(editTp[strategyId] ?? 15),
        stop_loss_pct: Number(editSl[strategyId] ?? 8),
        horizon_days: horizon,
        add_capital_usd: addCap > 0 ? Math.min(100, addCap) : undefined,
      });
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onMonitor() {
    if (!token) return;
    setDashBusy(true);
    try {
      await runPaperMonitor(token, true);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Monitor failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onBacktest(strategyId: string, period: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      const res = await runPaperBacktest(token, { strategy_id: strategyId, period });
      const result = (res.result || res) as Record<string, unknown>;
      const net = result.net_pnl_pct ?? result.net_pnl_usd;
      const summary =
        `${period.toUpperCase()} · net ` +
        (typeof net === "number"
          ? result.net_pnl_pct != null
            ? preciseNumber(net, "%")
            : money(net)
          : "done");
      setStrategyBacktests((prev) => ({ ...prev, [strategyId]: summary }));
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onAddCapital(strategyId: string) {
    if (!token) return;
    const add = Math.min(100, Math.max(1, Number(editAddCap[strategyId] || 0)));
    if (!add) return;
    setDashBusy(true);
    try {
      await addPaperStrategyCapital(token, strategyId, add);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add capital failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onAnalyze(symbol: string) {
    if (!token || !symbol) return;
    setDashBusy(true);
    try {
      const data = (await analyzePaperAsset(token, symbol, 100)) as Record<string, unknown>;
      const analysis = (data.analysis || {}) as Record<string, unknown>;
      const synth = (analysis.synthesis || {}) as Record<string, unknown>;
      setLastAnalysis(
        `${data.symbol || symbol} · $${data.live_price_usd ?? "—"} · ${String(synth.action || "n/a")}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analyze failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onLivePnl(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      const pnl = (await fetchStrategyLivePnl(token, strategyId)) as Record<string, unknown>;
      const summary =
        `${strategyId} · ${pnl.status} · sleeve ${money(pnl.sleeve_market_value_usd as number)} · ` +
        `uPnL ${money(pnl.unrealized_pnl_usd as number)} ` +
        `(${preciseNumber(pnl.unrealized_pnl_pct as number, "%")})`;
      setStrategyLivePnl((prev) => ({ ...prev, [strategyId]: summary }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Live PnL failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onLiquidate(strategyId: string) {
    if (!token) return;
    setLiquidateBusy(true);
    try {
      await liquidatePaperStrategy(token, strategyId);
      setDepositTick((t) => t + 1);
      setLiquidateStrategyId(null);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Liquidate failed");
    } finally {
      setLiquidateBusy(false);
    }
  }

  async function onRetryFailedBuys(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      const res = (await retryPaperStrategy(token, strategyId)) as Record<string, unknown>;
      setLastRetryMsg(typeof res.message === "string" ? res.message : "Retry finished.");
      setDepositTick((t) => t + 1);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setDashBusy(false);
    }
  }

  async function onDismiss(strategyId: string) {
    if (!token) return;
    setDashBusy(true);
    try {
      await dismissPaperStrategy(token, strategyId);
      await refreshDashboard();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dismiss failed");
    } finally {
      setDashBusy(false);
    }
  }

  const port = dashboard?.portfolio;
  const positions = port?.positions || [];
  const hours = Math.round((health?.monitor_interval_seconds || dashboard?.monitor_interval_seconds || 14400) / 3600);
  const freeSol =
    hfBalances?.balances?.find((b) => b.token === "SOL")?.available ?? null;

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">{HEDGE_FUND.description}</p>
        <p className="mt-2 font-mono text-xs text-signal">
          18-analyst · live trading · max $100 USD/sleeve · min $5/asset (SOL-funded) · 1% start / 10% profit · monitor every{" "}
          {hours}h ·{" "}
          <Link href="/agents/hedge-fund/pricing" className="underline hover:text-foreground">
            Pricing
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
        <span className="text-signal">
          {health?.trading_wallet_configured ? "live wallet ready" : "wallet not configured"}
        </span>
        {freeSol != null && (
          <>
            <span>·</span>
            <span>{freeSol} SOL free</span>
          </>
        )}
        {dashBusy && <span className="text-muted-foreground">· refreshing…</span>}
      </div>

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      <HedgeFundDeposit
        cluster={HEDGE_FUND.cluster}
        authToken={token}
        refreshTick={depositTick}
        onBalancesChange={setHfBalances}
      />

      {/* Live / paper monitor */}
      <div className="grid gap-4 lg:grid-cols-4">
        <Panel title="Paper book (sim)">
          <div className="space-y-2 font-mono text-xs">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Cash</span>
              <span>{money(port?.cash_usd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Equity</span>
              <span>{money(port?.equity_usd)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">PnL</span>
              <span className={(port?.pnl_usd || 0) >= 0 ? "text-signal" : "text-warn"}>
                {money(port?.pnl_usd)} ({port?.pnl_pct ?? 0}%)
              </span>
            </div>
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                disabled={!token || dashBusy}
                onClick={() => void refreshDashboard()}
                className="flex-1 border border-grid px-2 py-1.5 text-[10px] uppercase disabled:opacity-40"
              >
                Refresh
              </button>
              <button
                type="button"
                disabled={!token || dashBusy}
                onClick={() => void onMonitor()}
                className="flex-1 border border-signal/40 bg-signal/10 px-2 py-1.5 text-[10px] uppercase text-signal disabled:opacity-40"
              >
                Run cycle
              </button>
            </div>
          </div>
        </Panel>
      </div>
      <p className="font-mono text-[11px] text-muted-foreground">
        Create strategies in chat after depositing SOL - propose assets, confirm, then live
        Jupiter fills show below. Minimum trading horizon is 3 days (shorter requests are
        raised to 3d). Expired sleeves auto-swap back to SOL (15m poll, also on server start).
      </p>

      {(() => {
        // A strategy only belongs on this tab once assets have actually
        // been bought — "pending" (unconfirmed) and "active but still
        // buying in the background, zero fills yet" are both chat-only.
        const strategiesWithActivity = new Set(
          (dashboard?.by_strategy || [])
            .filter(
              (b) =>
                (b.positions || []).length > 0 ||
                (b.live_trades || []).length > 0 ||
                (b.trades || []).length > 0
            )
            .map((b) => b.strategy.id)
        );
        const visibleStrategies = (dashboard?.strategies || []).filter(
          (s) => s.status !== "pending" && (s.status !== "active" || strategiesWithActivity.has(s.id))
        );
        return (
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Strategies">
          <div className="max-h-72 space-y-3 overflow-y-auto">
            {visibleStrategies.length === 0 && (
              <p className="font-mono text-xs text-muted-foreground">
                No bought strategies yet — pending/still-buying proposals only show in chat.
              </p>
            )}
            {visibleStrategies.map((s) => {
              const mode = s.trading_mode || s.rules?.trading_mode || "live";
              return (
              <div key={s.id} className="border border-grid bg-surface/30 p-3 font-mono text-[11px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-signal">
                    {s.name} · {mode}/{s.mode}/{s.status} · {s.horizon_days || s.rules?.horizon_days || "open"}d
                  </span>
                  <span className="text-muted-foreground">{s.id}</span>
                </div>
                <p className="mt-1 text-muted-foreground">{(s.symbols || []).join(", ")}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {(s.status === "active" || s.status === "paused") && (
                    <>
                      <button
                        type="button"
                        disabled={!token || dashBusy}
                        onClick={() => void onLivePnl(s.id)}
                        className="border border-grid px-2 py-0.5 uppercase disabled:opacity-40"
                      >
                        Live PnL
                      </button>
                      <button
                        type="button"
                        disabled={!token || dashBusy}
                        onClick={() => setLiquidateStrategyId(s.id)}
                        className="border border-warn/40 px-2 py-0.5 uppercase text-warn disabled:opacity-40"
                      >
                        Liquidate to SOL
                      </button>
                    </>
                  )}
                  <span>TP</span>
                  <input
                    className="w-14 border border-grid bg-background px-1 py-0.5"
                    value={editTp[s.id] ?? String(s.rules?.take_profit_pct ?? 15)}
                    onChange={(e) => setEditTp((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  />
                  <span>SL</span>
                  <input
                    className="w-14 border border-grid bg-background px-1 py-0.5"
                    value={editSl[s.id] ?? String(s.rules?.stop_loss_pct ?? 8)}
                    onChange={(e) => setEditSl((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  />
                  <span>Days</span>
                  <input
                    className="w-14 border border-grid bg-background px-1 py-0.5"
                    placeholder="min 3"
                    value={
                      editHorizon[s.id] ??
                      (s.horizon_days == null && s.rules?.horizon_days == null
                        ? ""
                        : String(s.horizon_days ?? s.rules?.horizon_days ?? ""))
                    }
                    onChange={(e) => setEditHorizon((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  />
                  <span>Add$</span>
                  <input
                    className="w-14 border border-grid bg-background px-1 py-0.5"
                    placeholder="0"
                    value={editAddCap[s.id] ?? ""}
                    onChange={(e) => setEditAddCap((prev) => ({ ...prev, [s.id]: e.target.value }))}
                  />
                  <button
                    type="button"
                    disabled={!token || dashBusy}
                    onClick={() => void onSaveRules(s.id)}
                    className="border border-grid px-2 py-0.5 uppercase disabled:opacity-40"
                  >
                    Save
                  </button>
                  {(s.status === "active" || s.status === "paused") && (
                    <button
                      type="button"
                      disabled={!token || dashBusy || !Number(editAddCap[s.id] || 0)}
                      onClick={() => void onAddCapital(s.id)}
                      className="border border-signal/30 px-2 py-0.5 text-signal disabled:opacity-40"
                    >
                      Add cap
                    </button>
                  )}
                  {(s.symbols || []).slice(0, 2).map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      disabled={!token || dashBusy}
                      onClick={() => void onAnalyze(sym)}
                      className="border border-grid px-2 py-0.5 uppercase disabled:opacity-40"
                    >
                      Ax {sym}
                    </button>
                  ))}
                  {(["1w", "1m", "6m", "1y"] as const).map((p) => (
                    <button
                      key={p}
                      type="button"
                      disabled={!token || dashBusy}
                      onClick={() => void onBacktest(s.id, p)}
                      className="border border-signal/30 px-2 py-0.5 text-signal disabled:opacity-40"
                    >
                      BT {p}
                    </button>
                  ))}
                </div>
                {strategyLivePnl[s.id] && (
                  <div className="mt-2 border border-signal/30 bg-signal/5 px-2 py-1.5 text-signal">
                    Live PnL: {strategyLivePnl[s.id]}
                  </div>
                )}
                {strategyBacktests[s.id] && (
                  <div className="mt-2 border border-grid bg-background/50 px-2 py-1.5 text-muted-foreground">
                    Backtest: {strategyBacktests[s.id]}
                  </div>
                )}
                <CloseTxLinks
                  txs={s.rules?.liquidation_txs}
                  trades={(dashboard?.by_strategy || []).find((b) => b.strategy.id === s.id)?.live_trades}
                  swapped={Boolean(s.rules?.swapped_to_usdc)}
                />
              </div>
            );
            })}
            {lastAnalysis && <p className="font-mono text-[11px] text-signal">Analysis: {lastAnalysis}</p>}
            {lastRetryMsg && <p className="font-mono text-[11px] text-signal">Retry: {lastRetryMsg}</p>}
          </div>
        </Panel>

        <Panel title="Overlapping assets">
          <div className="max-h-72 space-y-2 overflow-y-auto font-mono text-[11px]">
            {Object.keys(dashboard?.overlapping_assets || {}).length === 0 ? (
              <p className="text-muted-foreground">No shared tickers across strategies yet.</p>
            ) : (
              Object.entries(dashboard?.overlapping_assets || {}).map(([sym, sids]) => (
                <div key={sym} className="border-b border-grid/40 pb-1.5">
                  <span className="text-signal">{sym}</span>{" "}
                  <span className="text-muted-foreground">→ {sids.join(", ")}</span>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>
        );
      })()}

      {(dashboard?.failed_strategies || []).length > 0 && (
        <Panel title="Failed strategies (dismiss to clear)">
          <div className="max-h-48 space-y-2 overflow-y-auto">
            {(dashboard?.failed_strategies || []).map((s) => (
              <div key={s.id} className="border border-warn/40 bg-warn/5 p-3 font-mono text-[11px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-warn">
                    {s.name || s.id} · failed · {(s.symbols || []).join(", ")}
                  </span>
                  <button
                    type="button"
                    disabled={!token || dashBusy}
                    onClick={() => void onDismiss(s.id)}
                    className="border border-warn/40 px-2 py-0.5 uppercase text-warn disabled:opacity-40"
                  >
                    Dismiss
                  </button>
                </div>
                <p className="mt-1 text-muted-foreground">{s.last_error || "Could not buy tokens/stocks"}</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">{s.id}</p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="By strategy — positions, live trades, paper trades">
        <div className="max-h-[28rem] space-y-4 overflow-y-auto">
          {(dashboard?.by_strategy || []).length === 0 && (
            <p className="font-mono text-xs text-muted-foreground">Create a strategy to see sleeves.</p>
          )}
          {(dashboard?.by_strategy || []).map((block) => {
            const s = block.strategy;
            const mode = block.trading_mode || s.trading_mode || s.rules?.trading_mode || "live";
            const liveTrades = (block.live_trades || []).filter(
              (t) => String(t.side || "").toUpperCase() !== "FEE"
            );
            return (
              <div key={s.id} className="border border-grid bg-surface/20 p-3 font-mono text-[11px]">
                <div className="mb-2 flex flex-wrap justify-between gap-2 text-signal">
                  <span>
                    {s.name} · {mode} · {s.status}
                    {s.status === "closed"
                      ? ""
                      : ` · sleeve ${money(block.sleeve_value_usd)}`}{" "}
                    · horizon {block.horizon_days || s.horizon_days || "open"}d
                  </span>
                  <span className="text-muted-foreground">{s.id}</span>
                </div>
                {(s.status === "closed" || block.closed) && (
                  <div className="mb-2 border border-grid/60 bg-background/40 px-2 py-1.5">
                    <span className="text-muted-foreground">Closed PnL · </span>
                    <span
                      className={
                        (block.realized_pnl_usd ?? 0) >= 0 ? "text-signal" : "text-warn"
                      }
                    >
                      {money(block.realized_pnl_usd)}
                      {block.realized_pnl_pct != null ? ` (${block.realized_pnl_pct}%)` : ""}
                    </span>
                    {block.liquidation_proceeds_usd != null && (
                      <span className="text-muted-foreground">
                        {" "}
                        · proceeds {money(block.liquidation_proceeds_usd)}
                      </span>
                    )}
                    {block.capital_usd != null && (
                      <span className="text-muted-foreground">
                        {" "}
                        · capital {money(block.capital_usd)}
                      </span>
                    )}
                    {block.perf_fee_usd != null && Number(block.perf_fee_usd) > 0 && (
                      <span className="text-muted-foreground">
                        {" "}
                        · fee {money(block.perf_fee_usd)}
                      </span>
                    )}
                  </div>
                )}
                <p className="mb-2 text-muted-foreground">Assets: {(block.symbols || []).join(", ") || "—"}</p>
                {(s.rules?.deploy_errors || []).length > 0 && (
                  <div className="mb-2 space-y-1">
                    {(s.rules?.deploy_errors || []).map((e, i) => (
                      <p key={i} className="text-warn">
                        {e.symbol ? `${e.symbol}: ` : ""}
                        {e.error || "Buy failed"}
                      </p>
                    ))}
                    {mode === "live" && (s.status === "active" || s.status === "paused") && (
                      <button
                        type="button"
                        disabled={!token || dashBusy}
                        onClick={() => void onRetryFailedBuys(s.id)}
                        className="border border-signal/40 px-2 py-0.5 uppercase text-signal disabled:opacity-40"
                      >
                        Retry failed buys
                      </button>
                    )}
                  </div>
                )}
                <div className="grid gap-3 md:grid-cols-3">
                  <div>
                    <div className="mb-1 text-muted-foreground">Positions</div>
                    {(block.positions || []).length === 0 && <p>—</p>}
                    {(block.positions || []).map((p) => (
                      <div key={`${s.id}-${p.symbol}`}>
                        {p.symbol} {Number(p.units).toPrecision(3)} · PnL {money(p.unrealized_pnl_usd)}
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="mb-1 text-muted-foreground">
                      {mode === "live" ? "Live trades · tx" : "Paper trades"}
                    </div>
                    {mode === "live"
                      ? liveTrades.slice(0, 10).map((t, i) => {
                          const sig = t.signature ? String(t.signature) : "";
                          const href =
                            t.explorer_url ||
                            (sig ? explorerUrlForSignature(sig, HEDGE_FUND.cluster) : "");
                          return (
                            <div key={t.id || i} className="mb-1.5 border-b border-grid/40 pb-1">
                              <div>
                                <span className={String(t.side).toUpperCase() === "ERROR" ? "text-warn" : ""}>
                                  {t.side} {t.symbol}
                                </span>{" "}
                                {money(t.notional_usd)}
                              </div>
                              {sig ? (
                                <a
                                  href={href}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="break-all text-[10px] text-signal hover:underline"
                                  title={sig}
                                >
                                  tx {sig.slice(0, 12)}…{sig.slice(-8)} ↗
                                </a>
                              ) : (
                                <span className="text-[10px] text-muted-foreground">no tx hash</span>
                              )}
                            </div>
                          );
                        })
                      : (block.trades || []).slice(0, 5).map((t, i) => (
                          <div key={t.id || i}>
                            {t.side} {t.symbol} {money(t.notional_usd)}
                          </div>
                        ))}
                    {mode === "live" && liveTrades.length === 0 && <p>—</p>}
                    {mode !== "live" && (block.trades || []).length === 0 && <p>—</p>}
                  </div>
                  <div>
                    <div className="mb-1 text-muted-foreground">Decisions</div>
                    {(block.decisions || []).slice(0, 5).map((d, i) => (
                      <div key={d.id || i}>
                        {d.action} {d.symbol}
                      </div>
                    ))}
                    {(block.decisions || []).length === 0 && <p>—</p>}
                  </div>
                </div>
                <CloseTxLinks
                  txs={block.liquidation_txs || s.rules?.liquidation_txs}
                  trades={liveTrades}
                  swapped={Boolean(s.rules?.swapped_to_usdc)}
                />
              </div>
            );
          })}
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Positions (all)">
          <div className="max-h-72 overflow-y-auto font-mono text-[11px]">
            {positions.length === 0 ? (
              <p className="text-muted-foreground">No open positions.</p>
            ) : (
              <table className="w-full text-left">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="pb-2 font-normal">Strategy</th>
                    <th className="pb-2 font-normal">Symbol</th>
                    <th className="pb-2 font-normal">Units</th>
                    <th className="pb-2 font-normal">Entry</th>
                    <th className="pb-2 font-normal">Mark</th>
                    <th className="pb-2 font-normal">PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {(dashboard?.by_strategy || []).flatMap((b) =>
                    (b.positions || []).map((p) => (
                      <tr key={`${b.strategy.id}-${p.symbol}-${p.id}`} className="border-t border-grid/60">
                        <td className="py-1.5 text-muted-foreground">{b.strategy.id}</td>
                        <td className="py-1.5 text-signal">{p.symbol}</td>
                        <td className="py-1.5">{Number(p.units).toPrecision(4)}</td>
                        <td className="py-1.5">{money(p.avg_entry_usd)}</td>
                        <td className="py-1.5">{money(p.mark_price_usd)}</td>
                        <td className={`py-1.5 ${(p.unrealized_pnl_usd || 0) >= 0 ? "text-signal" : "text-warn"}`}>
                          {money(p.unrealized_pnl_usd)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}
          </div>
        </Panel>

        <Panel title="Decisions">
          <div className="max-h-72 space-y-2 overflow-y-auto font-mono text-[11px]">
            {(dashboard?.decisions || []).length === 0 && (
              <p className="text-muted-foreground">No decisions yet — run a monitor cycle.</p>
            )}
            {(dashboard?.decisions || []).slice(0, 20).map((d, i) => (
              <div key={d.id || i} className="border-b border-grid/40 pb-1.5">
                <span className="text-muted-foreground">[{d.strategy_id}]</span>{" "}
                <span className="text-signal">{d.action}</span> {d.symbol}{" "}
                <span className="text-muted-foreground">
                  {d.created_at ? String(d.created_at).slice(0, 16) : ""} — {d.rationale}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Live trades (tx hash)">
          <div className="max-h-56 space-y-2 overflow-y-auto font-mono text-[11px]">
            {(dashboard?.live_trades || []).filter((t) => String(t.side).toUpperCase() !== "FEE").length ===
              0 && <p className="text-muted-foreground">No live Jupiter fills yet.</p>}
            {(dashboard?.live_trades || [])
              .filter((t) => String(t.side).toUpperCase() !== "FEE")
              .slice(0, 25)
              .map((t, i) => {
                const sig = t.signature ? String(t.signature) : "";
                const href =
                  t.explorer_url || (sig ? explorerUrlForSignature(sig, HEDGE_FUND.cluster) : "");
                return (
                  <div key={t.id || i} className="border-b border-grid/40 pb-1.5">
                    <div>
                      <span className="text-muted-foreground">[{t.strategy_id}]</span>{" "}
                      <span
                        className={
                          String(t.side).toUpperCase() === "ERROR" ? "text-warn" : "text-signal"
                        }
                      >
                        {t.side}
                      </span>{" "}
                      {t.symbol} {money(t.notional_usd)}
                    </div>
                    {sig ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="break-all text-[10px] text-signal hover:underline"
                      >
                        {sig} ↗
                      </a>
                    ) : (
                      <span className="text-[10px] text-muted-foreground">
                        {t.reason || "no tx hash"}
                      </span>
                    )}
                  </div>
                );
              })}
          </div>
        </Panel>
        <Panel title="Paper trades">
          <div className="max-h-56 space-y-2 overflow-y-auto font-mono text-[11px]">
            {(dashboard?.trades || []).length === 0 && (
              <p className="text-muted-foreground">No paper fills yet.</p>
            )}
            {(dashboard?.trades || []).slice(0, 20).map((t, i) => (
              <div key={t.id || i} className="border-b border-grid/40 pb-1.5">
                <span className="text-muted-foreground">[{t.strategy_id}]</span>{" "}
                <span className="text-signal">{t.side}</span> {t.symbol} {money(t.notional_usd)} @{" "}
                {money(t.price_usd)}{" "}
                <span className="text-muted-foreground">{t.reason}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={HEDGE_FUND.name} className="lg:col-span-2">
          <div className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Chat: propose → confirm hs… → live PnL for hs… · liquidate to SOL. Mock BT is historical only.
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
            {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Working…</div>}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  isAuthenticated
                    ? "e.g. Propose strategy AAPL XRP $50 · confirm hs… · analyze AAPL"
                    : "Connect wallet to chat"
                }
                disabled={!token || busy}
                className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-sm disabled:opacity-50"
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
                  className="border border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground hover:border-signal/40 disabled:opacity-40"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </Panel>

          {actions.length > 0 && (
            <Panel title="Tool activity">
              <div className="max-h-64 space-y-3 overflow-y-auto font-mono text-[11px]">
                {actions.map((action, idx) => (
                  <div key={`${action.tool}-${idx}`} className="border border-grid bg-surface/30 p-3">
                    <div className="mb-1 text-signal">{action.tool}</div>
                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                      {action.result.slice(0, 800)}
                    </pre>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {(dashboard?.market || []).length > 0 && (
            <Panel title="Shared market">
              <div className="space-y-1 font-mono text-[11px]">
                {(dashboard?.market || []).slice(0, 10).map((m) => (
                  <div key={m.symbol} className="flex justify-between border-b border-grid/40 py-1">
                    <span className="text-signal">{m.symbol}</span>
                    <span>
                      {money(m.price_usd)}{" "}
                      <span className={(m.change_24h_pct || 0) >= 0 ? "text-signal" : "text-warn"}>
                        {(m.change_24h_pct || 0).toFixed(2)}%
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in.
        </div>
      )}

      <ConfirmDialog
        open={Boolean(liquidateStrategyId)}
        onOpenChange={(open) => {
          if (!open && !liquidateBusy) setLiquidateStrategyId(null);
        }}
        title="Confirm liquidation to SOL"
        description={
          <div className="space-y-2">
            <p>
              This will sell every open position in{" "}
              <strong className="text-foreground">{liquidateStrategyId}</strong> through Jupiter
              and credit the proceeds to your SOL balance.
            </p>
            <p>
              A 10% performance fee is charged only if the completed strategy has a profit.
              This action cannot be undone.
            </p>
          </div>
        }
        confirmLabel="Liquidate to SOL"
        cancelLabel="Keep strategy"
        busy={liquidateBusy}
        onConfirm={() => {
          if (liquidateStrategyId) return onLiquidate(liquidateStrategyId);
        }}
      />
    </div>
  );
}
