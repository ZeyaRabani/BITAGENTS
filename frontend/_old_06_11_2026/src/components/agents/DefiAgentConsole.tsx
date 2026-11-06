"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { InstructionsDialog } from "@/components/agents/InstructionsDialog";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import {
  fetchDefiAgentHealth,
  mapDefiAgentActions,
  sendDefiAgentMessage,
  type DefiAgentHealth,
} from "@/lib/defiAgentClient";
import type { DefiAgentConfig } from "@/lib/defiAgentsConfig";
import {
  createDefiStrategy,
  loadDefiStrategies,
  updateDefiStrategyStatus,
  type DefiStrategyRecord,
} from "@/lib/defiStrategyStore";
import { getCustomInstructions, saveCustomInstructions } from "@/lib/customInstructionsClient";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { useWallet } from "@solana/wallet-adapter-react";

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

function ActionCard({ act, index }: { act: AgentAction; index: number }) {
  return (
    <div className="border border-grid bg-surface/30 p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-signal">
          {index + 1}. {act.tool}
        </span>
        {act.error && <span className="text-warn">error</span>}
      </div>
      <pre className="whitespace-pre-wrap break-all text-[11px] text-muted-foreground">
        {act.result || act.error || JSON.stringify(act.args ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export function DefiAgentConsole({ config }: { config: DefiAgentConfig }) {
  const { publicKey } = useWallet();
  const wallet = publicKey?.toBase58() ?? "";
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();

  const [health, setHealth] = useState<DefiAgentHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [strategies, setStrategies] = useState<DefiStrategyRecord[]>([]);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [strategyBusy, setStrategyBusy] = useState(false);
  const [strategyNote, setStrategyNote] = useState<string | null>(null);
  const [customInstructions, setCustomInstructions] = useState("");
  const [instructionsOpen, setInstructionsOpen] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  const defaults = useMemo(() => {
    const next: Record<string, string> = {};
    for (const field of config.strategyFields) {
      next[field.id] = field.defaultValue ?? "";
    }
    return next;
  }, [config.strategyFields]);

  useEffect(() => {
    setFieldValues(defaults);
    setMessages([]);
    setActions([]);
    setSessionId(undefined);
    setError(null);
    setStrategyNote(null);
  }, [config.slug, defaults]);

  useEffect(() => {
    void fetchDefiAgentHealth(config.slug).then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok" || h?.status === "degraded");
    });
  }, [config.slug]);

  useEffect(() => {
    if (!wallet) {
      setStrategies([]);
      return;
    }
    setStrategies(loadDefiStrategies(config.slug, wallet));
  }, [config.slug, wallet]);

  useEffect(() => {
    if (!token) return;
    void getCustomInstructions(config.slug, token)
      .then(setCustomInstructions)
      .catch(() => undefined);
  }, [config.slug, token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    actionsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [actions]);

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
      const data = await sendDefiAgentMessage(
        config.slug,
        messageWithInstructions,
        token,
        sessionId,
        history
      );
      setSessionId(data.session_id);
      setActions((prev) => [...prev, ...mapDefiAgentActions(data.actions)]);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: data.reply },
      ]);
      setAgentOnline(true);
      if (wallet) setStrategies(loadDefiStrategies(config.slug, wallet));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setAgentOnline(false);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: "assistant", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void runCommand(input);
  }

  function onCreateStrategy(e: FormEvent) {
    e.preventDefault();
    if (!wallet) {
      setError("Connect your wallet to create a strategy.");
      return;
    }
    setStrategyBusy(true);
    setError(null);
    try {
      const missing = config.strategyFields.find((field) => !(fieldValues[field.id] ?? "").trim());
      if (missing) {
        setError(`Fill in ${missing.label}.`);
        return;
      }
      const next = createDefiStrategy(config.slug, wallet, fieldValues, `${config.name} strategy`);
      setStrategies(next);
      setStrategyNote("Strategy saved. Tell the agent to arm or review it in chat.");
      void runCommand(
        `Create or update my ${config.name} strategy with params: ${JSON.stringify(fieldValues)}`
      );
    } finally {
      setStrategyBusy(false);
    }
  }

  async function onSaveInstructions(instructions: string) {
    if (!token) return;
    try {
      await saveCustomInstructions(config.slug, instructions, token);
      setCustomInstructions(instructions);
      setInstructionsOpen(false);
    } catch {
      setError("Failed to save custom instructions.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className={`inline-flex items-center gap-2 ${agentOnline ? "text-signal" : "text-warn"}`}>
          <span
            className={`h-1.5 w-1.5 rounded-full ${agentOnline ? "bg-signal animate-pulse-dot" : "bg-warn"}`}
          />
          {agentOnline ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{health?.model ?? config.model}</span>
        <span>·</span>
        <span>{config.cluster}</span>
        <span>·</span>
        <span className="text-signal">{config.pricePerTask}</span>
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
      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet above to fund strategies and chat with {config.name}.
        </div>
      )}
      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to use {config.name}.
        </div>
      )}

      <Panel title={`${config.strategyTitle} · capital & rules`}>
        <form onSubmit={onCreateStrategy} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {config.strategyFields.map((field) => (
            <label
              key={field.id}
              className="flex flex-col gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
            >
              {field.label}
              {field.type === "select" ? (
                <select
                  value={fieldValues[field.id] ?? ""}
                  onChange={(e) =>
                    setFieldValues((prev) => ({ ...prev, [field.id]: e.target.value }))
                  }
                  disabled={strategyBusy}
                  className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground disabled:opacity-50"
                >
                  {(field.options ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type === "number" ? "number" : "text"}
                  value={fieldValues[field.id] ?? ""}
                  onChange={(e) =>
                    setFieldValues((prev) => ({ ...prev, [field.id]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  disabled={strategyBusy}
                  className="border border-grid bg-background px-3 py-2 font-mono text-sm normal-case tracking-normal text-foreground disabled:opacity-50"
                />
              )}
            </label>
          ))}
          <div className="flex items-end">
            <button
              type="submit"
              disabled={!wallet || strategyBusy}
              className="w-full bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-primary-foreground disabled:opacity-40"
            >
              {strategyBusy ? "Saving…" : config.submitLabel}
            </button>
          </div>
        </form>
        {strategyNote && <p className="mt-3 font-mono text-[11px] text-signal">{strategyNote}</p>}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel
          title={`Command ${config.name}`}
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
                Set strategy parameters above, then chat in natural language - same flow as the DCA Agent.
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
                  {msg.role === "user" ? "You" : config.assistantLabel}
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
                placeholder={token ? "e.g. Check my strategy status" : "Sign in with wallet to chat"}
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
            {config.examplePrompts.map((prompt) => (
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
                Tool calls from {config.name} appear here - quotes, risk checks, strategy updates, and
                execution notes.
              </p>
            )}
            {actions.map((act, index) => (
              <ActionCard key={`${act.tool}-${index}`} act={act} index={index} />
            ))}
            <div ref={actionsEndRef} />
          </div>
        </Panel>
      </div>

      <Panel title="Strategies · local">
        {strategies.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No strategies yet. Create one above to track rules for this agent.
          </p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {strategies.map((strategy) => (
              <div key={strategy.id} className="border border-grid bg-surface/30 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                      {strategy.id}
                    </div>
                    <div className="mt-1 font-mono text-xs text-signal">{strategy.status}</div>
                  </div>
                  <div className="flex gap-2">
                    {strategy.status === "active" ? (
                      <button
                        type="button"
                        className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground"
                        onClick={() =>
                          wallet &&
                          setStrategies(
                            updateDefiStrategyStatus(config.slug, wallet, strategy.id, "paused")
                          )
                        }
                      >
                        Pause
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-signal hover:text-foreground"
                        onClick={() =>
                          wallet &&
                          setStrategies(
                            updateDefiStrategyStatus(config.slug, wallet, strategy.id, "active")
                          )
                        }
                      >
                        Resume
                      </button>
                    )}
                    <button
                      type="button"
                      className="border border-grid px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground hover:border-warn hover:text-warn"
                      onClick={() =>
                        wallet &&
                        setStrategies(
                          updateDefiStrategyStatus(config.slug, wallet, strategy.id, "closed")
                        )
                      }
                    >
                      Close
                    </button>
                  </div>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-2 font-mono text-[11px]">
                  {Object.entries(strategy.params).map(([key, value]) => (
                    <div key={key}>
                      <dt className="text-muted-foreground">{key}</dt>
                      <dd className="truncate text-foreground">{value || "-"}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
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
