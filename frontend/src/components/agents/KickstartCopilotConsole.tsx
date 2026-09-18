"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { InstructionsDialog } from "@/components/agents/InstructionsDialog";
import {
  fetchKickstartHealth,
  mapKickstartActions,
  sendKickstartMessage,
  type KickstartHealth,
} from "@/lib/kickstartCopilotClient";
import { KICKSTART_COPILOT, KICKSTART_EXAMPLE_PROMPTS } from "@/lib/kickstartCopilotConfig";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { EasyaTradingDeposit } from "@/components/agents/EasyaTradingDeposit";
import { EasyaOrderPanel } from "@/components/agents/EasyaOrderPanel";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { findLatestConfirmationRequired, type ConfirmationDetails } from "@/lib/dcaActionResults";
import { useWallet } from "@solana/wallet-adapter-react";
import { getCustomInstructions, saveCustomInstructions } from "@/lib/customInstructionsClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

function TradingConfirmDetailsView({ details }: { details?: ConfirmationDetails }) {
  if (!details) return null;

  if (
    details.action === "place_limit_buy" ||
    details.action === "place_threshold_buy" ||
    details.action === "place_market_buy" ||
    details.action === "cancel_trading_order"
  ) {
    return (
      <dl className="mt-3 space-y-2 border-t border-grid pt-3 font-mono text-[11px]">
        <div className="grid grid-cols-[110px_1fr] gap-1">
          {details.order_type && (
            <>
              <dt className="text-muted-foreground">Type</dt>
              <dd className="uppercase text-foreground">{details.order_type}</dd>
            </>
          )}
          {details.input_token && (
            <>
              <dt className="text-muted-foreground">From</dt>
              <dd>{details.input_token}</dd>
            </>
          )}
          {details.output_token && (
            <>
              <dt className="text-muted-foreground">To</dt>
              <dd>
                {details.output_token}{" "}
                {details.output_mint && (
                  <code className="block break-all text-[10px] text-foreground">{details.output_mint}</code>
                )}
              </dd>
            </>
          )}
          {details.amount_sol != null && (
            <>
              <dt className="text-muted-foreground">SOL amount</dt>
              <dd>{details.amount_sol}</dd>
            </>
          )}
          {details.limit_price_usd != null && (
            <>
              <dt className="text-muted-foreground">Limit price</dt>
              <dd>${details.limit_price_usd}</dd>
            </>
          )}
          {details.limit_market_cap_usd != null && (
            <>
              <dt className="text-muted-foreground">Limit market cap</dt>
              <dd>${details.limit_market_cap_usd.toLocaleString()}</dd>
            </>
          )}
          {details.current_price_usd != null && (
            <>
              <dt className="text-muted-foreground">Current price</dt>
              <dd>${details.current_price_usd}</dd>
            </>
          )}
          {details.current_market_cap_usd != null && (
            <>
              <dt className="text-muted-foreground">Current market cap</dt>
              <dd>${details.current_market_cap_usd.toLocaleString()}</dd>
            </>
          )}
          {details.trigger_condition && (
            <>
              <dt className="text-muted-foreground">Buy when</dt>
              <dd>{details.trigger_condition}</dd>
            </>
          )}
          {details.stop_condition && details.stop_condition !== "Stops when SOL runs out or max executions reached" && (
            <>
              <dt className="text-muted-foreground">Stop when</dt>
              <dd>{details.stop_condition}</dd>
            </>
          )}
          {details.executions != null && (
            <>
              <dt className="text-muted-foreground">Executions</dt>
              <dd>
                {details.action === "place_threshold_buy"
                  ? details.max_executions != null
                    ? `Up to ${details.max_executions} buys`
                    : "Until SOL runs out"
                  : `${details.executions} (one-time buy)`}
              </dd>
            </>
          )}
          {(details.check_interval_seconds != null || details.check_interval_minutes != null) && (
            <>
              <dt className="text-muted-foreground">Check interval</dt>
              <dd>{formatCheckInterval(details)}</dd>
            </>
          )}
          {details.max_executions != null && details.action === "place_threshold_buy" && (
            <>
              <dt className="text-muted-foreground">Max buys</dt>
              <dd>{details.max_executions}</dd>
            </>
          )}
          {details.slippage_bps != null && (
            <>
              <dt className="text-muted-foreground">Slippage</dt>
              <dd>{details.slippage_bps} bps</dd>
            </>
          )}
          {details.platform_fee != null && (
            <>
              <dt className="text-muted-foreground">Platform fee</dt>
              <dd>
                {details.platform_fee} SOL (0.1%)
              </dd>
            </>
          )}
          {details.total_cost != null && (
            <>
              <dt className="text-muted-foreground">Total cost</dt>
              <dd>{details.total_cost} SOL (swap + fee)</dd>
            </>
          )}
          {details.total_cost_per_buy != null && (
            <>
              <dt className="text-muted-foreground">Cost per buy</dt>
              <dd>{details.total_cost_per_buy} SOL (swap + fee)</dd>
            </>
          )}
          {details.order_id && (
            <>
              <dt className="text-muted-foreground">Order ID</dt>
              <dd>{details.order_id}</dd>
            </>
          )}
        </div>
      </dl>
    );
  }

  return null;
}

function formatCheckInterval(details: ConfirmationDetails) {
  if (details.check_interval_seconds != null) {
    const seconds = details.check_interval_seconds;
    if (seconds < 60) return `Every ${seconds}s`;
    if (seconds % 60 === 0) {
      const mins = seconds / 60;
      return mins === 1 ? "Every 1 min" : `Every ${mins} min`;
    }
    return `Every ${seconds}s`;
  }
  if (details.check_interval_minutes != null) {
    return details.check_interval_minutes === 1
      ? "Every 1 min"
      : `Every ${details.check_interval_minutes} min`;
  }
  return null;
}

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

function ActionCard({ act, index }: { act: AgentAction; index: number }) {
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
        <span className={isError ? "text-warn" : "text-signal"}>
          {isError ? "✗ error" : "✓ done"}
        </span>
      </div>
      {isError && act.error && (
        <div className="mt-2 border border-warn/30 bg-warn/10 px-3 py-2 font-mono text-[11px] text-warn">
          {act.error}
        </div>
      )}
      <pre className="mt-2 max-h-40 overflow-auto text-[10px] leading-relaxed text-foreground/80">
        {act.result}
      </pre>
    </div>
  );
}

export function KickstartCopilotConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [health, setHealth] = useState<KickstartHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [dataRefreshTick, setDataRefreshTick] = useState(0);
  const [agentConfirmOpen, setAgentConfirmOpen] = useState(false);
  const [agentConfirmMessage, setAgentConfirmMessage] = useState<string | null>(null);
  const [agentConfirmDetails, setAgentConfirmDetails] = useState<ConfirmationDetails | undefined>();
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [customInstructions, setCustomInstructions] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchKickstartHealth().then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
    });
  }, []);

  useEffect(() => {
    if (token) {
      void getCustomInstructions("easya", token)
        .then((instr) => setCustomInstructions(instr))
        .catch((err) => console.error("Failed to load custom instructions:", err));
    }
  }, [token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    actionsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [actions]);

  async function runCommand(text: string) {
    if (!token || !text.trim()) return;
    setBusy(true);
    setError(null);
    const trimmed = text.trim();
    const messageWithInstructions = customInstructions.trim()
      ? `[Custom Instructions: ${customInstructions.trim()}]\n\n${trimmed}`
      : trimmed;
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await sendKickstartMessage(messageWithInstructions, token, sessionId, history);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
      const mapped = mapKickstartActions(res.actions);
      setActions(mapped);
      setDataRefreshTick((tick) => tick + 1);

      const pendingConfirm = findLatestConfirmationRequired(mapped);
      if (pendingConfirm) {
        setAgentConfirmMessage(pendingConfirm.message);
        setAgentConfirmDetails(pendingConfirm.details);
        setAgentConfirmOpen(true);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { id: `e-${Date.now()}`, role: "assistant", content: msg },
      ]);
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

  async function onSaveInstructions(instructions: string) {
    if (!token) return;
    try {
      await saveCustomInstructions("easya", instructions, token);
      setCustomInstructions(instructions);
      setInstructionsOpen(false);
    } catch (err) {
      console.error("Failed to save custom instructions:", err);
      alert("Failed to save custom instructions. Please try again.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {KICKSTART_COPILOT.description} Connect your wallet (free) and ask about token overview,
          analytics, health scores, risks, comparisons, and launch operations.
        </p>
      </div>

      {/* <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={`inline-flex items-center gap-2 ${agentOnline ? "text-signal" : "text-warn"}`}>
          <span
            className={`h-1.5 w-1.5 rounded-full ${agentOnline ? "bg-signal animate-pulse-dot" : "bg-warn"}`}
          />
          {agentOnline ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? KICKSTART_COPILOT.model}</span>
        <span>·</span>
        <span className="text-signal">Free · wallet sign-in required</span>
      </div> */}

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
          Approve the wallet sign-in message to use the EasyA Analysis Agent (free).
        </div>
      )}

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in and chat with the copilot.
        </div>
      )}

      {publicKey && token && (
        <EasyaTradingDeposit
          cluster={KICKSTART_COPILOT.cluster}
          authToken={token}
          refreshTick={dataRefreshTick}
        />
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel 
          title="EasyA Analysis Agent" 
          className="lg:col-span-2"
          action={
            <button
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
                Ask for token overviews, live analytics, health scores, risk analysis, comparisons,
                and launch guidance.
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
                  {msg.role === "user" ? "You" : "Copilot"}
                </div>
                <div className="space-y-1">{formatReply(msg.content)}</div>
              </div>
            ))}
            {busy && (
              <div className="animate-pulse font-mono text-xs text-muted-foreground">Analyzing…</div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy || !token}
                placeholder={token ? "e.g. Give me an overview of BITAGENTS" : "Sign in with wallet to chat"}
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
            {KICKSTART_EXAMPLE_PROMPTS.map((prompt) => (
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

        <Panel title="Tool trace">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Developer view
          </p>
          <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1 font-mono text-xs">
            {actions.length === 0 && (
              <p className="text-muted-foreground">
                Token search, analytics, health, and watchlist tool calls appear here.
              </p>
            )}
            {actions.map((act, index) => (
              <ActionCard key={`${act.id}-${index}`} act={act} index={index} />
            ))}
            <div ref={actionsEndRef} />
          </div>
        </Panel>
      </div>

      {token && (
        <EasyaOrderPanel
          authToken={token}
          cluster={KICKSTART_COPILOT.cluster}
          refreshTick={dataRefreshTick}
        />
      )}

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to start chatting.
        </div>
      )}

      <ConfirmDialog
        open={agentConfirmOpen}
        onOpenChange={(open) => {
          setAgentConfirmOpen(open);
          if (!open) {
            setAgentConfirmMessage(null);
            setAgentConfirmDetails(undefined);
          }
        }}
        title="Confirm trading order"
        description={
          <>
            <p className="whitespace-pre-wrap">
              {agentConfirmMessage ?? "Please confirm before the agent places this order."}
            </p>
            <TradingConfirmDetailsView details={agentConfirmDetails} />
          </>
        }
        confirmLabel="Yes, proceed"
        cancelLabel="No, cancel"
        busy={busy}
        onCancel={() => {
          setAgentConfirmOpen(false);
          setAgentConfirmMessage(null);
          setAgentConfirmDetails(undefined);
          void runCommand("no, cancel");
        }}
        onConfirm={() => {
          setAgentConfirmOpen(false);
          setAgentConfirmMessage(null);
          setAgentConfirmDetails(undefined);
          void runCommand("yes, confirm");
        }}
      />

      <InstructionsDialog
        open={instructionsOpen}
        onOpenChange={setInstructionsOpen}
        instructions={customInstructions}
        onSave={onSaveInstructions}
      />
    </div>
  );
}
