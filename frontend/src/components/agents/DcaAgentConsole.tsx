"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DcaAgentDeposit } from "@/components/agents/DcaAgentDeposit";
import { DcaPlanPanel } from "@/components/agents/DcaPlanPanel";
import { InstructionsDialog } from "@/components/agents/InstructionsDialog";
import { explorerUrlForSignature, findLatestConfirmationRequired, mergeTransactions, type ConfirmationDetails } from "@/lib/dcaActionResults";
import { DCA_AGENT, DCA_EXAMPLE_PROMPTS } from "@/lib/dcaAgentSimulation";
import {
  fetchDcaAgentHealth,
  mapApiActions,
  sendDcaAgentMessage,
  type AgentAction,
  type DcaAgentHealth,
  type ParsedTransaction,
} from "@/lib/dcaAgentClient";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { useWallet } from "@solana/wallet-adapter-react";
import type { UserDepositBalances } from "@/lib/dcaWalletClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  errors?: string[];
  transactions?: ParsedTransaction[];
};

function ConfirmDetailsView({ details }: { details?: ConfirmationDetails }) {
  if (!details) return null;

  if (details.action === "create_dca_plan") {
    return (
      <dl className="mt-3 space-y-2 border-t border-grid pt-3 font-mono text-[11px]">
        <div className="grid grid-cols-[100px_1fr] gap-1">
          <dt className="text-muted-foreground">From</dt>
          <dd>
            {details.input_token}{" "}
            {details.input_mint && (
              <code className="block break-all text-[10px] text-foreground">{details.input_mint}</code>
            )}
          </dd>
          <dt className="text-muted-foreground">To</dt>
          <dd>
            {details.output_token}{" "}
            {details.output_mint && (
              <code className="block break-all text-[10px] text-foreground">{details.output_mint}</code>
            )}
          </dd>
          <dt className="text-muted-foreground">Amount</dt>
          <dd>{details.amount_per_buy}</dd>
          <dt className="text-muted-foreground">Interval</dt>
          <dd>{details.interval}</dd>
          {details.max_executions != null && (
            <>
              <dt className="text-muted-foreground">Max buys</dt>
              <dd>{details.max_executions}</dd>
            </>
          )}
          {details.total_budget != null && (
            <>
              <dt className="text-muted-foreground">Budget</dt>
              <dd>
                {details.total_budget} {details.input_token}
              </dd>
            </>
          )}
          {details.platform_fee_per_buy != null && (
            <>
              <dt className="text-muted-foreground">Fee / buy</dt>
              <dd>
                {details.platform_fee_per_buy} {details.platform_fee_token ?? details.input_token}{" "}
                (0.5%)
              </dd>
            </>
          )}
          {details.total_cost_per_buy != null && (
            <>
              <dt className="text-muted-foreground">Total / buy</dt>
              <dd>
                {details.total_cost_per_buy} {details.input_token} (swap + fee)
              </dd>
            </>
          )}
        </div>
      </dl>
    );
  }

  if (details.action === "execute_swap_buy" || details.action === "withdraw_user_tokens") {
    return (
      <dl className="mt-3 space-y-2 border-t border-grid pt-3 font-mono text-[11px]">
        <div className="grid grid-cols-[100px_1fr] gap-1">
          <dt className="text-muted-foreground">Token</dt>
          <dd>
            {details.input_token ?? details.token}{" "}
            {(details.input_mint ?? details.mint) && (
              <code className="block break-all text-[10px] text-foreground">
                {details.input_mint ?? details.mint}
              </code>
            )}
          </dd>
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
          <dt className="text-muted-foreground">Amount</dt>
          <dd>{details.amount ?? details.amount_per_buy}</dd>
        </div>
      </dl>
    );
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

      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all text-[10px] leading-relaxed text-muted-foreground">
        {JSON.stringify(act.args, null, 2)}
      </pre>
      {act.result && (
        <pre className="mt-2 max-h-40 overflow-auto border-t border-grid pt-2 text-[10px] leading-relaxed text-foreground/80">
          {act.result}
        </pre>
      )}
    </div>
  );
}

export function DcaAgentConsole() {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [health, setHealth] = useState<DcaAgentHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [transactions, setTransactions] = useState<ParsedTransaction[]>([]);
  const [userBalances, setUserBalances] = useState<UserDepositBalances | null>(null);
  const [agentConfirmOpen, setAgentConfirmOpen] = useState(false);
  const [agentConfirmMessage, setAgentConfirmMessage] = useState<string | null>(null);
  const [agentConfirmDetails, setAgentConfirmDetails] = useState<ConfirmationDetails | undefined>();
  const [dataRefreshTick, setDataRefreshTick] = useState(0);
  const [instructionsOpen, setInstructionsOpen] = useState(false);
  const [customInstructions, setCustomInstructions] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  const cluster = health?.cluster ?? DCA_AGENT.cluster;

  useEffect(() => {
    void fetchDcaAgentHealth(true).then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
      setMessages([
        {
          id: "welcome",
          role: "assistant",
          content: h
            ? h.llm_reachable === false
              ? `Connected to DCA agent API, but the hosted LLM is unreachable`
              : `Connected to DCA agent. Ask me to create plans, or manage DCA schedules.`
            : "Connected to DCA agent API.",
        },
      ]);
    });
    // Load custom instructions from localStorage
    const saved = localStorage.getItem("dca_custom_instructions");
    if (saved) setCustomInstructions(saved);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    actionsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [actions]);

  function onSaveInstructions(instructions: string) {
    setCustomInstructions(instructions);
    localStorage.setItem("dca_custom_instructions", instructions);
    setInstructionsOpen(false);
  }

  async function runCommand(command: string) {
    const trimmed = command.trim();
    if (!trimmed || busy) return;
    if (!token) {
      setError("Connect your wallet and approve the sign-in message first.");
      return;
    }

    // Prepend custom instructions to user message if they exist
    const messageWithInstructions = customInstructions.trim()
      ? `[Custom Instructions: ${customInstructions.trim()}]\n\n${trimmed}`
      : trimmed;

    setInput("");
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: trimmed }]);

    try {
      const data = await sendDcaAgentMessage(messageWithInstructions, token, sessionId);
      const mapped = mapApiActions(data.actions);
      const turnErrors = mapped.filter((a) => a.error).map((a) => a.error as string);
      const turnTxs = mapped.flatMap((a) => a.transactions);

      setSessionId(data.session_id);
      setActions((prev) => [...prev, ...mapped]);
      setTransactions((prev) => mergeTransactions(prev, turnTxs));

      const pendingConfirm = findLatestConfirmationRequired(mapped);
      if (pendingConfirm) {
        setAgentConfirmMessage(pendingConfirm.message);
        setAgentConfirmDetails(pendingConfirm.details);
        setAgentConfirmOpen(true);
      }

      setDataRefreshTick((tick) => tick + 1);

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: "assistant",
          content: data.reply,
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
          // content: `**Error:** ${message}\n\nMake sure the agents API is running (\`python agents_api.py\`) with \`HOSTED_MODEL_API_KEY\`, \`HOSTED_OLLAMA_URL\`, and \`DATABASE_URL\` set in \`agent/new/.env\`.`,
          content: `**Error** ${message}.`,
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

  return (
    <div className="space-y-6">
      {/* <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <Link href="/agents" className="transition hover:text-signal">
          ← Marketplace
        </Link>
        <span>·</span>
        <span className={`inline-flex items-center gap-2 ${agentOnline ? "text-signal" : "text-warn"}`}>
          <span
            className={`h-1.5 w-1.5 rounded-full ${agentOnline ? "bg-signal animate-pulse-dot" : "bg-warn"}`}
          />
          {agentOnline ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? DCA_AGENT.model}</span>
        <span>·</span>
        <span>{cluster}</span>
        {health?.wallet && (
          <>
            <span>·</span>
            <span className="truncate">
              {health.wallet.slice(0, 4)}…{health.wallet.slice(-4)}
            </span>
          </>
        )}
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
          Approve the wallet sign-in message to authenticate. The message includes acceptance of our Terms,
          Privacy Policy, and Risk Disclaimer.
        </div>
      )}

      <DcaAgentDeposit
        cluster={cluster}
        authToken={token}
        refreshTick={dataRefreshTick}
        onBalancesChange={setUserBalances}
      />

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above to deposit and run DCA plans tied to your balance.
        </div>
      )}

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to use the DCA agent.
        </div>
      )}

      {userBalances && userBalances.balances.length > 0 && (
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          <span className="text-foreground">
            {userBalances.user_wallet.slice(0, 4)}…{userBalances.user_wallet.slice(-4)}
          </span>
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
        <Panel 
          title="Command · DCA Agent" 
          className="lg:col-span-2"
          action={
            <button
              type="button"
              onClick={() => setInstructionsOpen(true)}
              className="border border-grid bg-surface/40 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground hover:border-signal/40 hover:text-signal"
            >
              Instructions
            </button>
          }
        >
          <div className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
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
              <div className="font-mono text-xs text-muted-foreground animate-pulse">
                Working… (AI Agent may take a moment)
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <label htmlFor="dca-command" className="sr-only">
              Command
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                id="dca-command"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy || !token}
                placeholder={token ? "e.g. Check my wallet status" : "Sign in with wallet to chat"}
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
            {DCA_EXAMPLE_PROMPTS.map((prompt) => (
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
          <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1 font-mono text-xs">
            {actions.length === 0 && (
              <p className="text-muted-foreground">
                Tool calls from the DCA agent appear here - wallet checks, quotes, plan updates, swaps, and tx
                signatures.
              </p>
            )}
            {actions.map((act, index) => (
              <ActionCard key={`${act.id}-${index}`} act={act} index={index} cluster={cluster} />
            ))}
            <div ref={actionsEndRef} />
          </div>
        </Panel>
      </div>

      <DcaPlanPanel authToken={token} cluster={cluster} refreshTick={dataRefreshTick} />

      <ConfirmDialog
        open={agentConfirmOpen}
        onOpenChange={(open) => {
          setAgentConfirmOpen(open);
          if (!open) {
            setAgentConfirmMessage(null);
            setAgentConfirmDetails(undefined);
          }
        }}
        title="Confirm DCA action"
        description={
          <>
            <p className="whitespace-pre-wrap">
              {agentConfirmMessage ?? "Please confirm before the agent proceeds."}
            </p>
            <ConfirmDetailsView details={agentConfirmDetails} />
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
