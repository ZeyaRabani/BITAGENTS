"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { VolumeAgentDeposit } from "@/components/agents/VolumeAgentDeposit";
import { VolumeCampaignPanel } from "@/components/agents/VolumeCampaignPanel";
import { VOLUME_AGENT, VOLUME_EXAMPLE_PROMPTS } from "@/lib/volumeAgentSimulation";
import {
  fetchVolumeAgentHealth,
  mapVolumeApiActions,
  mergeTransactions,
  sendVolumeAgentMessage,
  type AgentAction,
  type ParsedTransaction,
  type VolumeAgentHealth,
} from "@/lib/volumeAgentClient";
import { createVolumeCampaign } from "@/lib/volumePlanClient";
import { useVolumeWalletAuth } from "@/hooks/useVolumeWalletAuth";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import { useWallet } from "@solana/wallet-adapter-react";
import type { UserDepositBalances } from "@/lib/volumeWalletClient";

const BITAGENTS_MINT = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  errors?: string[];
  transactions?: ParsedTransaction[];
};

function formatReply(text: string) {
  return text.split("\n").map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return (
      <span key={i} className="block">
        {parts.map((part, j) => {
          if (part.startsWith("**") && part.endsWith("**")) {
            return (
              <strong key={j} className="font-semibold text-foreground">
                {part.slice(2, -2)}
              </strong>
            );
          }
          if (part.startsWith("`") && part.endsWith("`")) {
            return (
              <code key={j} className="rounded bg-surface-2 px-1 py-0.5 text-signal">
                {part.slice(1, -1)}
              </code>
            );
          }
          return <span key={j}>{part}</span>;
        })}
      </span>
    );
  });
}

function TxLink({ tx, cluster }: { tx: ParsedTransaction; cluster?: string }) {
  const href = tx.explorerUrl ?? explorerUrlForSignature(tx.signature, cluster);
  const short = `${tx.signature.slice(0, 8)}…${tx.signature.slice(-8)}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex flex-wrap items-center justify-between gap-2 border border-grid bg-surface/40 px-3 py-2 transition hover:border-signal"
    >
      <span className="font-mono text-[11px] text-foreground">{short}</span>
      <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
        {tx.status && (
          <span className={tx.status === "success" ? "text-signal" : "text-warn"}>{tx.status}</span>
        )}
        <span className="text-signal">Explorer ↗</span>
      </span>
    </a>
  );
}

function ActionCard({
  act,
  index,
  cluster,
}: {
  act: AgentAction;
  index: number;
  cluster?: string;
}) {
  const isError = act.status === "error";

  return (
    <div
      className={`border bg-background/60 p-3 ${
        isError ? "border-warn/50 bg-warn/5" : "border-grid"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={isError ? "text-warn" : "text-signal"}>
          [{index + 1}] {act.tool}
        </span>
        <span
          className={
            isError
              ? "text-warn"
              : act.status === "done"
                ? "text-signal"
                : "text-warn animate-pulse"
          }
        >
          {isError ? "✗ error" : act.status === "done" ? "✓ done" : act.status}
        </span>
      </div>

      {isError && act.error && (
        <div className="mt-2 border border-warn/30 bg-warn/10 px-3 py-2 font-mono text-[11px] leading-relaxed text-warn">
          {act.error}
        </div>
      )}

      {act.transactions.length > 0 && (
        <div className="mt-2 space-y-2 border-t border-grid pt-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Transaction{act.transactions.length > 1 ? "s" : ""}
          </div>
          {act.transactions.map((tx) => (
            <TxLink key={tx.signature} tx={tx} cluster={cluster} />
          ))}
        </div>
      )}

      {act.result && (
        <pre className="mt-2 max-h-40 overflow-auto border-t border-grid pt-2 text-[10px] leading-relaxed text-foreground/80">
          {act.result}
        </pre>
      )}
    </div>
  );
}

export function VolumeAgentConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useVolumeWalletAuth();
  const [health, setHealth] = useState<VolumeAgentHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [transactions, setTransactions] = useState<ParsedTransaction[]>([]);
  const [userBalances, setUserBalances] = useState<UserDepositBalances | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const [baseToken, setBaseToken] = useState(BITAGENTS_MINT);
  const [quoteToken, setQuoteToken] = useState("SOL");
  const [tradeAmount, setTradeAmount] = useState("0.01");
  const [interval, setInterval] = useState("1 minute");
  const [maxExecutions, setMaxExecutions] = useState("10");
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [campaignSuccess, setCampaignSuccess] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  const cluster = health?.cluster;

  useEffect(() => {
    void fetchVolumeAgentHealth().then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: h
            ? `Connected to Volume Agent. Deposit SOL, then create a campaign. Swaps use Jupiter — same path as BITAGENTS Volume. Platform fee is **${VOLUME_AGENT.platformFeeLabel}**.`
            : "Volume Agent API is offline. Start the agents API to continue.",
        },
      ]);
    });
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    actionsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [actions]);

  async function runCommand(command: string) {
    const trimmed = command.trim();
    if (!trimmed || busy) return;
    if (!token) {
      setError("Connect your wallet and approve the sign-in message first.");
      return;
    }

    setInput("");
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);

    try {
      const res = await sendVolumeAgentMessage(trimmed, token, sessionId);
      const mapped = mapVolumeApiActions(res.actions ?? []);
      const turnErrors = mapped.filter((a) => a.error).map((a) => a.error as string);
      const turnTxs = mapped.flatMap((a) => a.transactions);

      setSessionId(res.session_id);
      setActions((prev) => [...prev, ...mapped]);
      setTransactions((prev) => mergeTransactions(prev, turnTxs));

      if (mapped.some((a) => a.tool === "create_volume_campaign" || a.tool === "list_volume_campaigns")) {
        setRefreshTick((t) => t + 1);
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: res.reply,
          errors: turnErrors.length > 0 ? turnErrors : undefined,
          transactions: turnTxs.length > 0 ? turnTxs : undefined,
        },
      ]);
      setAgentOnline(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setError(message);
      setAgentOnline(false);
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: "assistant",
          content: `**Error:** ${message}`,
          errors: [message],
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void runCommand(input);
  }

  async function handleCreateCampaign(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setCampaignBusy(true);
    setCampaignError(null);
    setCampaignSuccess(null);

    try {
      const result = await createVolumeCampaign(
        {
          base_token: baseToken.trim(),
          quote_token: quoteToken.trim() || "SOL",
          trade_amount: Number(tradeAmount),
          interval: interval.trim(),
          max_executions: Number(maxExecutions),
        },
        token
      );
      setCampaignSuccess(result.message ?? `Campaign ${result.campaign.id} created.`);
      setRefreshTick((t) => t + 1);
    } catch (err) {
      setCampaignError(err instanceof Error ? err.message : "Campaign creation failed");
    } finally {
      setCampaignBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          {VOLUME_AGENT.description} Connect your wallet, deposit SOL, then schedule buy/sell
          volume cycles. Campaigns swap through Jupiter on tokens that already trade — no new
          pool setup. Defaults to BITAGENTS/SOL (same as BITAGENTS Volume). Platform fee is{" "}
          <strong className="text-foreground">{VOLUME_AGENT.platformFeeLabel}</strong>.
        </p>
        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          Just BITAGENTS volume?{" "}
          <a href="/agents/volume2" className="text-signal underline hover:text-foreground">
            Use the simplified presets page
          </a>
        </p>
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
          Approve the wallet sign-in message to authenticate. The message includes acceptance of our Terms,
          Privacy Policy, and Risk Disclaimer.
        </div>
      )}

      <VolumeAgentDeposit
        cluster={cluster}
        authToken={token}
        refreshTick={refreshTick}
        onBalancesChange={setUserBalances}
      />

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above to deposit and run volume campaigns tied to your balance.
        </div>
      )}

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to use the Volume Agent.
        </div>
      )}

      {userBalances && userBalances.balances.length > 0 && (
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          <span className="text-foreground">
            {userBalances.user_wallet.slice(0, 4)}…{userBalances.user_wallet.slice(-4)}
          </span>{" "}
          · {userBalances.balances.length} deposited token{userBalances.balances.length === 1 ? "" : "s"}
        </div>
      )}

      {transactions.length > 0 && (
        <Panel title="On-chain transactions · session">
          <div className="grid gap-2 sm:grid-cols-2">
            {transactions.map((tx) => (
              <TxLink key={tx.signature} tx={tx} cluster={cluster} />
            ))}
          </div>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Command · Volume Agent" className="lg:col-span-2">
          <div className="flex max-h-105 flex-col gap-4 overflow-y-auto pr-1">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`rounded border px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "border-grid bg-surface/60 text-foreground"
                    : msg.errors?.length
                      ? "border-warn/40 bg-warn/5 text-muted-foreground"
                      : "border-signal/30 bg-surface/30 text-muted-foreground"
                }`}
              >
                <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
                  {msg.role === "user" ? "You" : "Agent"}
                </div>
                <div className="space-y-1">{formatReply(msg.content)}</div>

                {msg.errors && msg.errors.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-warn/30 pt-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-warn">Error</div>
                    {msg.errors.map((err, i) => (
                      <p key={i} className="font-mono text-[11px] leading-relaxed text-warn">
                        {err}
                      </p>
                    ))}
                  </div>
                )}

                {msg.transactions && msg.transactions.length > 0 && (
                  <div className="mt-3 space-y-2 border-t border-grid pt-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                      Transaction{msg.transactions.length > 1 ? "s" : ""}
                    </div>
                    {msg.transactions.map((tx) => (
                      <TxLink key={tx.signature} tx={tx} cluster={cluster} />
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && (
              <div className="animate-pulse font-mono text-xs text-muted-foreground">
                Working… (Volume Agent may take a moment)
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
                placeholder={token ? "e.g. List my volume campaigns" : "Sign in with wallet to chat"}
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
            {VOLUME_EXAMPLE_PROMPTS.map((prompt) => (
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

        <Panel
          title="Agent actions · live"
          action={
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {!agentOnline && "Waiting"}
            </span>
          }
        >
          <div className="max-h-130 space-y-3 overflow-y-auto pr-1 font-mono text-xs">
            {actions.length === 0 && (
              <p className="text-muted-foreground">
                Campaign creation and swap tool calls appear here with tx signatures.
              </p>
            )}
            {actions.map((act, index) => (
              <ActionCard key={`${act.id}-${index}`} act={act} index={index} cluster={cluster} />
            ))}
            <div ref={actionsEndRef} />
          </div>
        </Panel>
      </div>

      <Panel title="Quick create · volume campaign">
        <form className="space-y-4" onSubmit={(e) => void handleCreateCampaign(e)}>
          <p className="text-sm text-muted-foreground">
            Defaults to BITAGENTS/SOL, same swap path as BITAGENTS Volume. No pool setup — Jupiter must
            already be able to route the pair. Set size, frequency, and cycle count, then start.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 font-mono text-[11px] sm:col-span-2">
              <span className="text-muted-foreground">Base token (symbol or mint)</span>
              <input
                className="w-full border border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                value={baseToken}
                onChange={(e) => setBaseToken(e.target.value)}
                placeholder="Symbol or mint (e.g. USDC)"
                required
              />
            </label>
            <label className="space-y-1 font-mono text-[11px]">
              <span className="text-muted-foreground">Quote token</span>
              <select
                className="w-full border border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                value={quoteToken}
                onChange={(e) => setQuoteToken(e.target.value)}
              >
                <option value="SOL">SOL</option>
                <option value="USDC">USDC</option>
              </select>
            </label>
            <label className="space-y-1 font-mono text-[11px]">
              <span className="text-muted-foreground">{quoteToken} per trade leg</span>
              <input
                className="w-full border border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                value={tradeAmount}
                onChange={(e) => setTradeAmount(e.target.value)}
                inputMode="decimal"
                required
              />
            </label>
            <label className="space-y-1 font-mono text-[11px]">
              <span className="text-muted-foreground">Interval</span>
              <input
                className="w-full border border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
                placeholder="30 seconds"
                required
              />
            </label>
            <label className="space-y-1 font-mono text-[11px]">
              <span className="text-muted-foreground">Cycles (buy + sell each)</span>
              <input
                className="w-full border border-grid bg-background px-3 py-2 text-foreground outline-none focus:border-signal"
                value={maxExecutions}
                onChange={(e) => setMaxExecutions(e.target.value)}
                inputMode="numeric"
                required
              />
            </label>
          </div>

          {campaignError && <p className="font-mono text-[11px] text-warn">{campaignError}</p>}
          {campaignSuccess && <p className="font-mono text-[11px] text-signal">{campaignSuccess}</p>}

          <button
            type="submit"
            disabled={!isAuthenticated || campaignBusy}
            className="bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {campaignBusy ? "Creating…" : "Create campaign"}
          </button>
        </form>
      </Panel>

      {token && (
        <VolumeCampaignPanel
          authToken={token}
          cluster={cluster}
          refreshTick={refreshTick}
          onCampaignChange={() => setRefreshTick((t) => t + 1)}
        />
      )}
    </div>
  );
}
