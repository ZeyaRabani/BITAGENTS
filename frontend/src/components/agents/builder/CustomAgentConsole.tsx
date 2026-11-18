"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { AppShell, Panel } from "@/components/AppShell";
import { BuildPanel } from "@/components/agents/builder/BuildPanel";
import {
  BTN_GHOST,
  BTN_GHOST_PLAIN,
  BTN_PRIMARY,
  CODE_BOX,
  Field,
  INPUT,
  LABEL,
  Notice,
  StatusBadge,
  WalletGate,
} from "@/components/agents/builder/BuilderUi";
import { LimitsPanel, StrategyPanel } from "@/components/agents/builder/SpecPanels";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  BuilderApiError,
  builderApi,
  errorText,
  formatAmount,
  formatScore,
  formatTime,
  formatUsd,
  isAbort,
  shortAddress,
  type AgentMode,
  type AomiState,
  type PerformanceBook,
  type BuilderAgent,
  type BuilderEvaluation,
  type BuilderHolding,
  type BuilderOrder,
  type BuilderRun,
  type BuilderSignal,
  type ChatEvent,
  type PaperBook,
} from "@/lib/builderClient";

const RUNS_REFRESH_MS = 30_000;

export function CustomAgentConsole({ agentId }: { agentId: string }) {
  const { publicKey } = useWallet();
  const { wallet, token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [agent, setAgent] = useState<BuilderAgent | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [aomi, setAomi] = useState<AomiState | null>(null);
  const [activityTick, setActivityTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setAgent(null);
    setLoadError(null);
    builderApi
      .get(agentId, controller.signal)
      .then(setAgent)
      .catch((err) => {
        if (!isAbort(err)) setLoadError(errorText(err));
      });
    return () => controller.abort();
  }, [agentId]);

  const onAgent = useCallback((next: BuilderAgent) => setAgent(next), []);
  const bumpActivity = useCallback(() => setActivityTick((tick) => tick + 1), []);

  if (!agent) {
    return (
      <AppShell title="Your strategy">
        {loadError ? (
          <div className="space-y-4">
            <Notice tone="warn">{loadError}</Notice>
            <Link href="/agents" className={BTN_GHOST}>
              Back to marketplace
            </Link>
          </div>
        ) : (
          <p className="font-mono text-xs text-muted-foreground">Loading strategy {agentId}…</p>
        )}
      </AppShell>
    );
  }

  const phantomAddress = publicKey?.toBase58() ?? null;

  return (
    <AppShell title={agent.spec.name} subtitle={agent.spec.description}>
      <div className="space-y-6">
        <Panel title="Strategy" action={<StatusBadge status={agent.build_status} />}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <Field label="Template">{agent.spec.strategy.template}</Field>
            <Field label="Build status">{agent.build_status}</Field>
            <Field label="Spec sha">{agent.spec_sha}</Field>
            <Field label="App name">{agent.build?.hosted?.app ?? agent.app_name}</Field>
            <Field label="Strategy id">{agent.id}</Field>
            <Field label="Owner">
              <span title={agent.owner_wallet}>{shortAddress(agent.owner_wallet)}</span>
            </Field>
          </div>
        </Panel>

        <ModePanel agent={agent} token={token} wallet={wallet} onAgent={onAgent} onChanged={bumpActivity} />

        <WalletGate
          authBusy={authBusy}
          authError={authError}
          isAuthenticated={isAuthenticated}
          purpose="check signals, use the agent wallet and chat"
        />

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="min-w-0 space-y-6 lg:col-span-2">
            <SignalsPanel
              agentId={agent.id}
              token={token}
              quote={agent.spec.limits.quote}
              defaultWallet={aomi?.wallet?.address ?? phantomAddress}
              defaultWalletSource={aomi?.wallet?.address ? "Aomi agent wallet" : phantomAddress ? "connected wallet" : null}
              onRun={bumpActivity}
            />
            {!aomi?.hosted && (
              <ChatPanel agentId={agent.id} token={token} quote={agent.spec.limits.quote} onReply={bumpActivity} />
            )}
            {agent.mode === "paper" && (
              <PerformancePanel agentId={agent.id} quote={agent.spec.limits.quote} refreshTick={activityTick} />
            )}
            <RunLogPanel agentId={agent.id} quote={agent.spec.limits.quote} refreshTick={activityTick} />
            {!agent.build?.hosted && <SourcePanel agentId={agent.id} buildStatus={agent.build_status} />}
          </div>
          <div className="min-w-0 space-y-6">
            <AomiWalletPanel
              agentId={agent.id}
              token={token}
              quote={agent.spec.limits.quote}
              refreshTick={activityTick}
              state={aomi}
              onState={setAomi}
            />
            <LimitsPanel limits={agent.spec.limits} />
            <StrategyPanel agent={agent} />
            <BuildPanel agent={agent} token={token} wallet={wallet} onAgent={onAgent} />
          </div>
        </div>

        <LegalSignInNotice />
      </div>
    </AppShell>
  );
}

// ------------------------------------------------------------------- mode

const MODE_COPY: Record<AgentMode, { label: string; text: string }> = {
  paper: {
    label: "Paper",
    text: "Runs build the real swap and simulate it on Solana mainnet. Nothing is sent and no funds are needed.",
  },
  live: {
    label: "Live",
    text: "Runs are staged for the agent wallet to sign. The wallet needs USDC and SOL.",
  },
};

function ModeBadge({ mode }: { mode: AgentMode }) {
  return (
    <span
      className={`inline-flex border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] ${
        mode === "live" ? "border-warn/60 text-warn" : "border-signal/50 text-signal"
      }`}
    >
      {MODE_COPY[mode].label}
    </span>
  );
}

function ModePanel({
  agent,
  token,
  wallet,
  onAgent,
  onChanged,
}: {
  agent: BuilderAgent;
  token: string | null;
  wallet: string | null;
  onAgent: (agent: BuilderAgent) => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mode: AgentMode = agent.mode ?? "paper";
  const isOwner = Boolean(wallet) && wallet === agent.owner_wallet;

  async function switchTo(next: AgentMode) {
    if (!token || busy || next === mode) return;
    if (
      next === "live" &&
      !window.confirm(
        "Switch this strategy to live? Live runs are staged for the agent wallet to sign and spend real funds."
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onAgent(await builderApi.setAgentMode(agent.id, next, token));
      onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Mode" action={<ModeBadge mode={mode} />}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">{MODE_COPY[mode].label}.</span> {MODE_COPY[mode].text}
        </p>
        {isOwner && (
          <div className="flex shrink-0 items-center gap-2">
            {(["paper", "live"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => void switchTo(option)}
                disabled={busy || !token}
                aria-pressed={option === mode}
                className={
                  option === mode
                    ? "border border-signal px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-signal disabled:opacity-40"
                    : BTN_GHOST
                }
              >
                {MODE_COPY[option].label}
              </button>
            ))}
          </div>
        )}
      </div>
      {isOwner && !token && (
        <p className="mt-2 font-mono text-xs text-muted-foreground">Sign in with your wallet to switch mode.</p>
      )}
      {busy && <p className="mt-2 animate-pulse font-mono text-xs text-muted-foreground">Switching mode…</p>}
      {error && <p className="mt-2 break-words font-mono text-xs text-warn">{error}</p>}
    </Panel>
  );
}

// ----------------------------------------------------------------- orders

const USDC_DECIMALS = 6;

/** What was lent to the wallet inside the simulation, or null when nothing was. */
function lentText(order: BuilderOrder, quote: string, tokenDecimals: number | undefined): string | null {
  const lent = order.simulation?.lent_in_simulation;
  if (!lent) return null;
  const parts: string[] = [];
  if (lent.input_raw > 0) {
    if (order.side === "buy") {
      // Buys spend the quote token (USDC, 6 decimals).
      parts.push(`${formatAmount(lent.input_raw / 10 ** USDC_DECIMALS)} ${quote}`);
    } else if (tokenDecimals != null) {
      parts.push(`${formatAmount(lent.input_raw / 10 ** tokenDecimals)} ${order.token_symbol || order.symbol}`);
    } else {
      parts.push(order.token_symbol || order.symbol);
    }
  }
  if (lent.sol > 0) parts.push(`${formatAmount(lent.sol)} SOL`);
  return parts.length ? `Simulated with ${parts.join(" and ")} lent in-simulation` : null;
}

/** One order from a preview, a run or a chat tool result. Paper orders show the simulation, never "staged". */
function OrderRow({
  order,
  quote,
  tokenDecimals,
}: {
  order: BuilderOrder;
  quote: string;
  tokenDecimals?: number;
}) {
  const sim = order.simulation;
  const fill = order.paper_fill;
  const token = order.token_symbol || order.symbol;
  const status = order.build_error
    ? { label: "Build failed", tone: "text-warn" }
    : sim
      ? { label: "Simulated", tone: "text-muted-foreground" }
      : order.stage
        ? { label: "Built for signing", tone: "text-muted-foreground" }
        : { label: "Would place", tone: "text-muted-foreground" };
  const lent = lentText(order, quote, tokenDecimals);

  return (
    <div className="border border-grid px-3 py-2 font-mono text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className={`text-[10px] uppercase tracking-[0.14em] ${status.tone}`}>{status.label}</span>
        {sim && (
          <span className={`text-[10px] uppercase tracking-[0.14em] ${sim.ok ? "text-signal" : "text-warn"}`}>
            {sim.ok ? "Passed" : "Failed"}
          </span>
        )}
        <ActionBadge action={order.side} />
        <span className="text-foreground">{token}</span>
        <span className="text-foreground">{formatUsd(order.usd)}</span>
        <span className="break-words text-muted-foreground">{order.reason}</span>
      </div>
      {order.build_error && <p className="mt-2 break-words text-warn">{order.build_error}</p>}
      {sim && (
        <div className="mt-2 space-y-1">
          {fill ? (
            <p className="text-foreground">
              {order.side === "sell" ? "Sold" : "Bought"} {formatAmount(fill.tokens)} {token} for {formatUsd(fill.usd)}
              {fill.price_usd != null && ` at ${formatUsd(fill.price_usd)}`}
            </p>
          ) : (
            sim.ok && <p className="text-muted-foreground">No fill was booked to the paper balance.</p>
          )}
          <p className="text-muted-foreground">
            Slot {sim.slot ?? "-"} · {sim.units_consumed != null ? sim.units_consumed.toLocaleString("en-US") : "-"}{" "}
            compute units · not sent
          </p>
          {!sim.ok && <p className="break-all text-warn">{JSON.stringify(sim.error)}</p>}
          {lent && <p className="text-muted-foreground">{lent}</p>}
        </div>
      )}
    </div>
  );
}

function OrderList({
  orders,
  quote,
  holdings,
}: {
  orders: BuilderOrder[];
  quote: string;
  /** Holdings from the same result, used to find token decimals for sells. */
  holdings?: BuilderHolding[];
}) {
  return (
    <div className="space-y-2">
      {orders.map((order) => (
        <OrderRow
          key={order.index}
          order={order}
          quote={quote}
          tokenDecimals={holdings?.find((holding) => holding.mint === order.mint)?.decimals}
        />
      ))}
    </div>
  );
}

function PaperBalance({ paper, quote }: { paper: PaperBook; quote: string }) {
  return (
    <div className="space-y-3 border border-grid p-3">
      <div>
        <div className={LABEL}>Paper balance</div>
        <p className="mt-1 text-muted-foreground">Simulated funds. Not on-chain.</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label={`Cash (${quote})`}>{formatUsd(paper.cash_usd)}</Field>
        <Field label="Equity">{formatUsd(paper.equity_usd)}</Field>
        <Field label="Started with">{formatUsd(paper.start_usd)}</Field>
      </div>
      <div>
        <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Holdings</div>
        {paper.holdings.length === 0 ? (
          <p className="mt-1 text-muted-foreground">No holdings.</p>
        ) : (
          <div className="mt-1 space-y-1">
            {paper.holdings.map((holding) => (
              <div key={holding.mint} className="flex flex-wrap justify-between gap-x-4">
                <span className="text-foreground">
                  {formatAmount(holding.amount)} {holding.symbol}
                </span>
                <span className="text-muted-foreground">{formatUsd(holding.value_usd)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------ performance

function PerformancePanel({ agentId, quote, refreshTick }: { agentId: string; quote: string; refreshTick: number }) {
  const [books, setBooks] = useState<PerformanceBook[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      builderApi
        .performance(agentId, controller.signal)
        .then((res) => {
          setBooks(res.books);
          setFetchedAt(new Date());
          setError(null);
        })
        .catch((err) => {
          if (!isAbort(err)) setError(errorText(err));
        });
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [agentId, refreshTick]);

  return (
    <Panel title="Paper performance">
      <div className="space-y-3 font-mono text-xs">
        {error && <p className="break-words text-warn">{error}</p>}
        {!books && !error && <p className="text-muted-foreground">Loading…</p>}
        {books && books.length === 0 && (
          <p className="text-muted-foreground">No wallet has a paper position in this strategy yet.</p>
        )}
        {books?.map((book) => {
          const pct = book.start_usd ? (book.pnl_usd / book.start_usd) * 100 : 0;
          const up = book.pnl_usd >= 0;
          return (
            <div key={book.wallet} className="space-y-3 border border-grid p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <span className="text-foreground" title={book.wallet}>
                  {shortAddress(book.wallet)}
                </span>
                <span className={up ? "text-signal" : "text-warn"}>
                  {up ? "+" : "-"}
                  {formatUsd(Math.abs(book.pnl_usd))} ({up ? "+" : "-"}
                  {Math.abs(pct).toFixed(2)}%)
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <Field label="Equity">{formatUsd(book.equity_usd)}</Field>
                <Field label={`Cash (${quote})`}>{formatUsd(book.cash_usd)}</Field>
                <Field label="Started with">{formatUsd(book.start_usd)}</Field>
              </div>
              <div className="space-y-1">
                {book.holdings.map((holding) => (
                  <div key={holding.mint} className="flex flex-wrap justify-between gap-x-4">
                    <span className="text-foreground">
                      {formatAmount(holding.amount)} {holding.symbol}
                    </span>
                    <span className="text-muted-foreground">{formatUsd(holding.value_usd)}</span>
                  </div>
                ))}
              </div>
              {!book.priced && <p className="text-warn">A holding has no price right now, so equity is understated.</p>}
            </div>
          );
        })}
        <p className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
          Simulated funds, valued at current prices
          {fetchedAt ? ` · fetched ${fetchedAt.toLocaleTimeString()} · refreshes every 30 s` : ""}
        </p>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- signals

function ActionBadge({ action }: { action: string }) {
  const tone =
    action === "buy"
      ? "bg-signal text-primary-foreground"
      : action === "sell"
        ? "border border-warn/60 text-warn"
        : "border border-grid text-muted-foreground";
  return (
    <span className={`px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] ${tone}`}>
      {action}
    </span>
  );
}

function signalTone(signal: string) {
  return signal === "bullish" ? "text-signal" : signal === "bearish" ? "text-warn" : "text-muted-foreground";
}

function SignalRow({ signal }: { signal: BuilderSignal }) {
  const resolved = signal.token && "symbol" in signal.token ? signal.token : null;
  const tokenError = signal.token && "error" in signal.token ? signal.token.error : null;
  const counts = signal.signal_counts;
  const analysts = signal.analysts ?? [];
  const headlines = signal.headlines ?? [];

  return (
    <div className="border border-grid">
      <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3">
        <div className="flex min-w-0 items-center gap-3">
          {resolved?.icon && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resolved.icon} alt="" width={28} height={28} className="h-7 w-7 shrink-0 rounded-full" />
          )}
          <div className="min-w-0">
            <div className="font-display text-base font-bold">
              {resolved?.symbol ?? signal.symbol}
              {resolved && resolved.symbol !== signal.symbol && (
                <span className="ml-2 font-mono text-[10px] font-normal uppercase tracking-[0.14em] text-muted-foreground">
                  {signal.symbol}
                </span>
              )}
            </div>
            {resolved?.name && <div className="truncate text-xs text-muted-foreground">{resolved.name}</div>}
          </div>
        </div>
        <ActionBadge action={signal.action} />
      </div>

      <div className="grid grid-cols-2 gap-4 border-t border-grid px-3 py-3 sm:grid-cols-4">
        <Field label="Price">{formatUsd(signal.price)}</Field>
        {signal.kind ? (
          <>
            <Field label={`Change, ${signal.window_minutes} min`}>
              {signal.change_pct != null ? `${signal.change_pct >= 0 ? "+" : ""}${signal.change_pct.toFixed(2)}%` : "-"}
            </Field>
            <Field label="Role">{signal.kind === "trigger" ? "Trigger" : "Basket"}</Field>
            <Field label="Trigger">
              {signal.kind === "trigger" ? (
                <span className={signal.fired ? "text-signal" : "text-muted-foreground"}>
                  +{signal.threshold_pct}% · {signal.fired ? "fired" : "not fired"}
                </span>
              ) : (
                "-"
              )}
            </Field>
          </>
        ) : (
          <>
        <Field label="Composite score">{formatScore(signal.composite_score)}</Field>
        <Field label="Confidence">{signal.confidence ?? "-"}</Field>
        <Field label="Analysts">
          {counts ? (
            <span>
              <span className="text-signal">{counts.bullish} bullish</span>
              {" · "}
              <span className="text-warn">{counts.bearish} bearish</span>
              {" · "}
              <span className="text-muted-foreground">{counts.neutral} neutral</span>
            </span>
          ) : (
            "-"
          )}
        </Field>
          </>
        )}
      </div>

      <div className="border-t border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        as of {formatTime(signal.as_of)} · source {signal.data_source ?? "-"}
        {signal.bars != null && ` · ${signal.bars} bars`}
        {resolved?.usd_price != null && ` · token price ${formatUsd(resolved.usd_price)}`}
      </div>
      {tokenError && (
        <div className="border-t border-warn/30 px-3 py-2 font-mono text-xs text-warn">Token: {tokenError}</div>
      )}

      {analysts.length > 0 && (
        <details className="border-t border-grid">
          <summary className="cursor-pointer px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground">
            {analysts.length} analysts
          </summary>
          <div className="divide-y divide-[var(--grid)] border-t border-grid">
            {analysts.map((item, index) => (
              <div key={`${item.analyst}-${index}`} className="grid gap-1 px-3 py-2 font-mono text-xs sm:grid-cols-[11rem_6rem_1fr]">
                <div className="text-foreground">
                  {item.analyst}
                  <span className="ml-2 text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    {item.domain}
                  </span>
                </div>
                <div className={`uppercase tracking-[0.12em] ${signalTone(item.signal)}`}>
                  {item.signal} {item.confidence}
                </div>
                <div className="break-words text-muted-foreground">{item.reasoning}</div>
              </div>
            ))}
          </div>
        </details>
      )}

      {headlines.length > 0 && (
        <details className="border-t border-grid">
          <summary className="cursor-pointer px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground">
            {headlines.length} headlines
          </summary>
          <ul className="space-y-1 border-t border-grid px-3 py-2 text-xs text-muted-foreground">
            {headlines.map((headline, index) => (
              <li key={index}>{headline}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function SignalsPanel({
  agentId,
  token,
  quote,
  defaultWallet,
  defaultWalletSource,
  onRun,
}: {
  agentId: string;
  token: string | null;
  quote: string;
  defaultWallet: string | null;
  defaultWalletSource: string | null;
  onRun: () => void;
}) {
  const [override, setOverride] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<BuilderEvaluation | null>(null);

  const target = override.trim() || defaultWallet || "";

  async function check() {
    if (!token || !target) return;
    setBusy(true);
    setError(null);
    try {
      setEvaluation(await builderApi.preview(agentId, target, token));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
      onRun();
    }
  }

  const signals = evaluation?.signals ?? [];
  const notes = evaluation?.notes ?? [];
  const orders = evaluation?.orders ?? [];
  const evalWallet = evaluation?.wallet;

  return (
    <Panel title="Signals">
      <div className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={override}
            onChange={(event) => setOverride(event.target.value)}
            disabled={busy}
            spellCheck={false}
            placeholder={defaultWallet ?? "Solana wallet address to evaluate"}
            className={`${INPUT} min-w-0 flex-1 text-xs`}
          />
          <button
            type="button"
            onClick={() => void check()}
            disabled={busy || !token || !target}
            className={BTN_PRIMARY}
          >
            {busy ? "Checking…" : "Check signals now"}
          </button>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {override.trim()
            ? "Evaluating the address typed above."
            : defaultWallet
              ? `Evaluating the ${defaultWalletSource}: ${shortAddress(defaultWallet)}. Type an address to use another wallet.`
              : "No wallet address available. Connect a wallet or type an address."}
          {" "}Preview only reads data. It never builds a transaction.
        </p>
        {!token && (
          <p className="font-mono text-xs text-muted-foreground">Sign in with your wallet to check signals.</p>
        )}
        {busy && (
          <p className="animate-pulse font-mono text-xs text-muted-foreground">
            Waiting for the evaluation. This request usually takes 3 to 20 seconds.
          </p>
        )}
        {error && <Notice tone="warn">{error}</Notice>}

        {!evaluation && !busy && !error && (
          <p className="font-mono text-xs text-muted-foreground">No evaluation requested in this session yet.</p>
        )}

        {evaluation && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 border-t border-grid pt-4 sm:grid-cols-4">
              <Field label="Run id">{evaluation.run_id}</Field>
              {evalWallet && (
                <>
                  <Field label="Wallet">
                    <span title={evalWallet.address}>{shortAddress(evalWallet.address)}</span>
                  </Field>
                  <Field label={evaluation.mode === "paper" ? "Paper cash" : `Cash (${evalWallet.quote})`}>
                    {formatUsd(evalWallet.cash_usd)}
                  </Field>
                  <Field label={evaluation.mode === "paper" ? "Paper spent today" : "Spent today"}>
                    {formatUsd(evalWallet.spent_today_usd)}
                  </Field>
                </>
              )}
            </div>
            {evaluation.mode && (
              <p className="font-mono text-xs text-muted-foreground">
                {evaluation.mode === "paper"
                  ? "Paper mode. These balances are this wallet's paper balance, not on-chain funds."
                  : "Live mode. These balances are on-chain."}
              </p>
            )}

            {signals.length === 0 ? (
              <p className="font-mono text-xs text-muted-foreground">The evaluation returned no signals.</p>
            ) : (
              <div className="space-y-3">
                {signals.map((signal) => (
                  <SignalRow key={signal.symbol} signal={signal} />
                ))}
              </div>
            )}

            <div>
              <div className={LABEL}>Notes</div>
              {notes.length === 0 ? (
                <p className="mt-2 font-mono text-xs text-muted-foreground">No notes returned.</p>
              ) : (
                <ul className="mt-2 list-disc space-y-1 pl-5 font-mono text-xs text-muted-foreground">
                  {notes.map((note, index) => (
                    <li key={index} className="break-words">
                      {note}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <div className={LABEL}>Orders it would place</div>
              {orders.length === 0 ? (
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  No orders. The agent would not trade on this evaluation.
                </p>
              ) : (
                <div className="mt-2">
                  <OrderList orders={orders} quote={evalWallet?.quote ?? quote} holdings={evalWallet?.holdings} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------ aomi wallet

function HostedAomiPanel({
  hosted,
  ready,
  reason,
}: {
  hosted: NonNullable<AomiState["hosted"]>;
  ready: boolean;
  reason?: string;
}) {
  const [copied, setCopied] = useState<string | null>(null);

  async function copyPrompt(text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(text);
    window.setTimeout(() => setCopied(null), 1500);
  }

  return (
    <Panel title="Run on Aomi">
      <div className="space-y-3 font-mono text-xs">
        <p className={`uppercase tracking-[0.14em] ${ready ? "text-signal" : "text-warn"}`}>
          {ready ? "Deployed" : "Not deployed"}
        </p>
        {reason && <p className="break-words text-muted-foreground">{reason}</p>}
        <p className="text-muted-foreground">
          This strategy is run by the BIT Agents agent in Aomi. Your agent wallet, signing and schedule live there. Runs appear in the run log
          on this page.
        </p>
        <Field label="Aomi app">{hosted.app}</Field>
        <div>
          <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">To run it once, say this in Aomi</div>
          <p className="mt-1 break-all text-foreground">{hosted.prompt}</p>
          <button type="button" onClick={() => void copyPrompt(hosted.prompt)} className={`${BTN_GHOST} mt-2`}>
            {copied === hosted.prompt ? "Copied" : "Copy"}
          </button>
        </div>
        {hosted.schedule_prompt && (
          <div>
            <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              To keep it running, say this instead
            </div>
            <p className="mt-1 break-all text-foreground">{hosted.schedule_prompt}</p>
            <button
              type="button"
              onClick={() => void copyPrompt(hosted.schedule_prompt ?? "")}
              className={`${BTN_GHOST} mt-2`}
            >
              {copied === hosted.schedule_prompt ? "Copied" : "Copy"}
            </button>
            <p className="mt-2 text-muted-foreground">It does not run by itself until you schedule it in Aomi.</p>
          </div>
        )}
        {ready && (
          <a href={hosted.chat_url} target="_blank" rel="noreferrer" className={`${BTN_PRIMARY} inline-block`}>
            Open in Aomi
          </a>
        )}
      </div>
    </Panel>
  );
}

function AomiWalletPanel({
  agentId,
  token,
  quote,
  refreshTick,
  state,
  onState,
}: {
  agentId: string;
  token: string | null;
  quote: string;
  refreshTick: number;
  state: AomiState | null;
  onState: (state: AomiState | null) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [manualTick, setManualTick] = useState(0);

  useEffect(() => {
    if (!token) {
      onState(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    builderApi
      .aomi(agentId, token, controller.signal)
      .then((data) => {
        onState(data);
        setError(null);
      })
      .catch((err) => {
        if (isAbort(err)) return;
        onState(null);
        setError(errorText(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [agentId, token, refreshTick, manualTick, onState]);

  async function createWallet() {
    if (!token) return;
    setCreating(true);
    setCreateError(null);
    try {
      onState(await builderApi.createAomiWallet(agentId, token));
    } catch (err) {
      setCreateError(errorText(err));
    } finally {
      setCreating(false);
    }
  }

  async function copy(address: string) {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const address = state?.wallet?.address;

  if (state?.hosted) {
    return <HostedAomiPanel hosted={state.hosted} ready={state.connected} reason={state.reason} />;
  }

  return (
    <Panel
      title="Agent wallet (Aomi)"
      action={
        token ? (
          <button
            type="button"
            onClick={() => setManualTick((tick) => tick + 1)}
            disabled={loading}
            className={BTN_GHOST}
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        ) : undefined
      }
    >
      <div className="space-y-3 font-mono text-xs">
        {!token && <p className="text-muted-foreground">Sign in with your wallet to see your agent wallet.</p>}
        {token && !state && !error && <p className="text-muted-foreground">Loading agent wallet…</p>}

        {error && (
          <>
            <p className="uppercase tracking-[0.14em] text-warn">Not connected</p>
            <p className="break-words text-warn">{error}</p>
          </>
        )}

        {state && (
          <>
            <p className={`uppercase tracking-[0.14em] ${state.connected ? "text-signal" : "text-warn"}`}>
              {state.connected ? "Connected" : "Not connected"}
            </p>
            {state.reason && <p className="break-words text-muted-foreground">{state.reason}</p>}
            {(state.app || state.lane) && (
              <div className="grid grid-cols-2 gap-4">
                {state.app && <Field label="Aomi app">{state.app}</Field>}
                {state.lane && <Field label="Lane">{state.lane}</Field>}
              </div>
            )}
            {state.wallet && address ? (
              <>
                <div>
                  <div className="text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Address</div>
                  <p className="mt-1 break-all text-foreground">{address}</p>
                  <button type="button" onClick={() => void copy(address)} className={`${BTN_GHOST} mt-2`}>
                    {copied ? "Copied" : "Copy address"}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <Field label="On-chain SOL">{state.wallet.sol ?? "-"}</Field>
                  <Field label={`On-chain ${quote}`}>{state.wallet.cash_usd ?? "-"}</Field>
                </div>
                {state.mode === "paper" && (
                  <p className="text-muted-foreground">Paper runs do not use these on-chain funds.</p>
                )}
                {state.paper && <PaperBalance paper={state.paper} quote={quote} />}
              </>
            ) : (
              <>
                <p className="text-muted-foreground">No agent wallet exists for this strategy yet.</p>
                <button
                  type="button"
                  onClick={() => void createWallet()}
                  disabled={creating}
                  className={BTN_PRIMARY}
                >
                  {creating ? "Creating…" : "Create agent wallet"}
                </button>
              </>
            )}
          </>
        )}
        {createError && <p className="break-words text-warn">{createError}</p>}
      </div>
    </Panel>
  );
}

// ------------------------------------------------------------------- chat

/** The run tool returns the evaluation as JSON text. Null when the event is not a run or the text was cut. */
function runResultOf(event: ChatEvent): BuilderEvaluation | null {
  if (!event.result) return null;
  try {
    const data: unknown = JSON.parse(event.result);
    if (data && typeof data === "object" && Array.isArray((data as BuilderEvaluation).orders)) {
      return data as BuilderEvaluation;
    }
  } catch {
    // Not JSON, or cut by the server's 6000 character limit.
  }
  return null;
}

function ChatRunResult({ result, quote }: { result: BuilderEvaluation; quote: string }) {
  const orders = result.orders ?? [];
  return (
    <div className="mt-2 space-y-2">
      {result.mode && (
        <p className="text-muted-foreground">
          {result.mode === "paper" ? "Paper run. Nothing was sent." : "Live run."}
        </p>
      )}
      {orders.length === 0 ? (
        <p className="text-muted-foreground">No orders.</p>
      ) : (
        <OrderList orders={orders} quote={result.wallet?.quote ?? quote} holdings={result.wallet?.holdings} />
      )}
      {result.paper && (
        <p className="text-muted-foreground">
          Paper balance: cash {formatUsd(result.paper.cash_usd)} · equity {formatUsd(result.paper.equity_usd)}
        </p>
      )}
    </div>
  );
}

type ChatLine =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "agent"; content: string; events: ChatEvent[] }
  | { id: string; role: "system"; content: string };

function ChatPanel({
  agentId,
  token,
  quote,
  onReply,
}: {
  agentId: string;
  token: string | null;
  quote: string;
  onReply: () => void;
}) {
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const seq = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [lines, busy]);

  const nextId = () => `line-${(seq.current += 1)}`;

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || !token) return;
    setBusy(true);
    setInput("");
    setLines((current) => [...current, { id: nextId(), role: "user", content: message }]);
    try {
      const data = await builderApi.chat(agentId, { message, session_id: sessionId }, token);
      if (data.session_id) setSessionId(data.session_id);
      setLines((current) => [
        ...current,
        { id: nextId(), role: "agent", content: data.reply ?? "", events: data.events ?? [] },
      ]);
    } catch (err) {
      const prefix = err instanceof BuilderApiError && err.status ? `HTTP ${err.status}: ` : "";
      const text = err instanceof Error ? err.message : String(err);
      setLines((current) => [...current, { id: nextId(), role: "system", content: `${prefix}${text}` }]);
    } finally {
      setBusy(false);
      onReply();
    }
  }

  return (
    <Panel
      title="Chat"
      action={
        sessionId ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            session {shortAddress(sessionId)}
          </span>
        ) : undefined
      }
    >
      <div ref={listRef} className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
        {lines.length === 0 && (
          <p className="font-mono text-xs text-muted-foreground">No messages in this session yet.</p>
        )}
        {lines.map((line) => (
          <div
            key={line.id}
            className={`rounded border px-4 py-3 text-sm leading-relaxed ${
              line.role === "user"
                ? "border-grid bg-surface/60 text-foreground"
                : line.role === "system"
                  ? "border-warn/40 bg-warn/5 text-warn"
                  : "border-signal/30 bg-surface/30 text-muted-foreground"
            }`}
          >
            <div
              className={`mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] ${
                line.role === "system" ? "text-warn" : "text-signal"
              }`}
            >
              {line.role === "user" ? "You" : line.role === "system" ? "System" : "Agent"}
            </div>
            {line.role === "agent" && !line.content ? (
              <p className="font-mono text-xs">The agent returned an empty reply.</p>
            ) : (
              <p className={`whitespace-pre-wrap break-words ${line.role === "system" ? "font-mono text-xs" : ""}`}>
                {line.content}
              </p>
            )}
            {line.role === "agent" && line.events.length > 0 && (
              <div className="mt-3 space-y-2 border-t border-grid pt-3">
                {line.events.map((item, index) => {
                  const runResult = runResultOf(item);
                  return (
                  <div key={index} className="font-mono text-[11px] leading-relaxed">
                    <span className="uppercase tracking-[0.14em] text-signal">{item.type}</span>
                    {item.tool && <span className="ml-2 text-foreground">{item.tool}</span>}
                    {item.summary && (
                      <p className="mt-0.5 whitespace-pre-wrap break-words text-muted-foreground">{item.summary}</p>
                    )}
                    {runResult && <ChatRunResult result={runResult} quote={quote} />}
                    {item.signature && (
                      <a
                        href={`https://solscan.io/tx/${item.signature}`}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-0.5 block truncate text-foreground underline"
                      >
                        {item.signature}
                      </a>
                    )}
                  </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Waiting for the agent…</div>}
      </div>
      <form onSubmit={send} className="mt-4 border-t border-grid pt-4">
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={busy || !token}
            placeholder={token ? "Message the agent" : "Sign in with wallet to chat"}
            className={`${INPUT} min-w-0 flex-1`}
          />
          <button type="submit" disabled={busy || !input.trim() || !token} className={BTN_PRIMARY}>
            Send
          </button>
        </div>
      </form>
    </Panel>
  );
}

// ---------------------------------------------------------------- run log

function RunLogPanel({ agentId, quote, refreshTick }: { agentId: string; quote: string; refreshTick: number }) {
  const [runs, setRuns] = useState<BuilderRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  const [manualTick, setManualTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => {
      setLoading(true);
      builderApi
        .runs(agentId, controller.signal)
        .then((data) => {
          const sorted = [...(data.runs ?? [])].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
          );
          setRuns(sorted);
          setError(null);
          setFetchedAt(new Date());
        })
        .catch((err) => {
          if (!isAbort(err)) setError(errorText(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    };
    load();
    const timer = setInterval(load, RUNS_REFRESH_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [agentId, refreshTick, manualTick]);

  return (
    <Panel
      title="Run log"
      action={
        <button
          type="button"
          onClick={() => setManualTick((tick) => tick + 1)}
          disabled={loading}
          className={BTN_GHOST}
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      }
    >
      <div className="space-y-3">
        {error && <Notice tone="warn">{error}</Notice>}
        {!runs && !error && <p className="font-mono text-xs text-muted-foreground">Loading runs…</p>}
        {runs && runs.length === 0 && (
          <p className="font-mono text-xs text-muted-foreground">This strategy has no recorded runs.</p>
        )}
        {runs && runs.length > 0 && (
          <div className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {runs.map((run) => {
              const notes = run.decision?.notes ?? [];
              const orders = run.orders ?? [];
              const orderCount = orders.length;
              const runMode = run.decision?.mode;
              const runPaper = run.decision?.paper;
              const runWallet = run.decision?.wallet;
              return (
                <div key={run.id} className="border border-grid px-3 py-2 font-mono text-xs">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                    <span className="text-foreground">{formatTime(run.created_at)}</span>
                    <span className="uppercase tracking-[0.14em] text-signal">{run.caller}</span>
                    {runMode && <ModeBadge mode={runMode} />}
                    <span className="text-muted-foreground" title={run.wallet}>
                      {shortAddress(run.wallet)}
                    </span>
                    <span className="text-muted-foreground">
                      {orderCount} {orderCount === 1 ? "order" : "orders"}
                    </span>
                    <span className="text-muted-foreground">
                      {!run.built
                        ? "preview, nothing built"
                        : runMode === "paper"
                          ? "simulated, nothing sent"
                          : "transactions built"}
                    </span>
                  </div>
                  {notes.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
                      {notes.map((note, index) => (
                        <li key={index} className="break-words">
                          {note}
                        </li>
                      ))}
                    </ul>
                  )}
                  {orderCount > 0 && (
                    <div className="mt-2">
                      <OrderList orders={orders} quote={runWallet?.quote ?? quote} holdings={runWallet?.holdings} />
                    </div>
                  )}
                  {runPaper && (
                    <p className="mt-2 text-muted-foreground">
                      Paper balance after this run: cash {formatUsd(runPaper.cash_usd)} · equity{" "}
                      {formatUsd(runPaper.equity_usd)}
                    </p>
                  )}
                  {run.error && <p className="mt-2 break-words text-warn">{run.error}</p>}
                </div>
              );
            })}
          </div>
        )}
        {fetchedAt && (
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Fetched {fetchedAt.toLocaleTimeString()} · refreshes every 30 s
          </p>
        )}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------- generated app

function SourcePanel({ agentId, buildStatus }: { agentId: string; buildStatus: string }) {
  const [files, setFiles] = useState<Record<string, string> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);

  // Re-fetch when the build status changes: sources appear after the first compile.
  useEffect(() => {
    const controller = new AbortController();
    builderApi
      .source(agentId, controller.signal)
      .then((data) => {
        setFiles(data.files ?? {});
        setError(null);
      })
      .catch((err) => {
        if (isAbort(err)) return;
        setFiles(null);
        setError(errorText(err));
      });
    return () => controller.abort();
  }, [agentId, buildStatus]);

  const names = files ? Object.keys(files) : [];
  const current = active && names.includes(active) ? active : (names[0] ?? null);

  return (
    <Panel title="Generated app">
      {error && <Notice tone="warn">{error}</Notice>}
      {!files && !error && <p className="font-mono text-xs text-muted-foreground">Loading source…</p>}
      {files && names.length === 0 && (
        <p className="font-mono text-xs text-muted-foreground">The server returned no source files.</p>
      )}
      {files && current && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {names.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => setActive(name)}
                className={
                  name === current
                    ? "border border-signal px-2.5 py-1.5 font-mono text-[10px] tracking-[0.06em] text-signal"
                    : BTN_GHOST_PLAIN
                }
              >
                {name}
              </button>
            ))}
          </div>
          <pre className={`${CODE_BOX} max-h-[520px]`}>{files[current]}</pre>
        </div>
      )}
    </Panel>
  );
}
