"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import {
  fetchKickstartHealth,
  mapKickstartActions,
  sendKickstartMessage,
  type KickstartHealth,
} from "@/lib/kickstartCopilotClient";
import { KICKSTART_COPILOT, KICKSTART_EXAMPLE_PROMPTS } from "@/lib/kickstartCopilotConfig";
import { EasyaTradingDeposit } from "@/components/agents/EasyaTradingDeposit";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { useWallet } from "@solana/wallet-adapter-react";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
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
  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchKickstartHealth().then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
    });
  }, []);

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
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text.trim() }]);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await sendKickstartMessage(text.trim(), token, sessionId, history);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
      setActions(mapKickstartActions(res.actions));
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
          Approve the wallet sign-in message to use the EasyA Analysis Agent (free).
        </div>
      )}

      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in and chat with the copilot.
        </div>
      )}

      <EasyaTradingDeposit authToken={token} refreshTick={messages.length} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
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
            Developer view · EASY Screener API calls
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

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to start chatting.
        </div>
      )}
    </div>
  );
}
