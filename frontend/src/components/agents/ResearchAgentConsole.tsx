"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import {
  fetchResearchAgentHealth,
  mapResearchAgentActions,
  sendResearchAgentMessage,
  type ResearchAgentHealth,
} from "@/lib/researchAgentClient";
import type { ResearchAgentConfig } from "@/lib/researchAgentsConfig";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import type { AgentAction } from "@/lib/dcaAgentClient";
import { useWallet } from "@solana/wallet-adapter-react";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

function formatReply(text: string) {
  const lines = text.split("\n");
  return lines.map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

type Props = {
  config: ResearchAgentConfig;
};

export function ResearchAgentConsole({ config }: Props) {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();
  const [health, setHealth] = useState<ResearchAgentHealth | null>(null);
  const [agentOnline, setAgentOnline] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const actionsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchResearchAgentHealth(config.slug).then((h) => {
      setHealth(h);
      setAgentOnline(h?.status === "ok");
    });
  }, [config.slug]);

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
      const res = await sendResearchAgentMessage(config.slug, text.trim(), token, sessionId, history);
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
      setActions(mapResearchAgentActions(res.actions));
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
      <div className="bg-surface/40 px-4 py-4">
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {config.description} Connect your wallet (free) to chat with the agent.
        </p>
      </div>

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
        <span className="text-signal">Free · wallet sign-in required</span>
      </div>

      {error && (
        <div className="bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}

      {authError && (
        <div className="bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {publicKey && authBusy && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to use {config.name} (free).
        </div>
      )}

      {!publicKey && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in and chat.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={config.name} className="lg:col-span-2">
          <div className="flex max-h-105 flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Try an example prompt or ask a question in natural language.
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
              <div className="animate-pulse font-mono text-xs text-muted-foreground">Thinking…</div>
            )}
            <div ref={chatEndRef} />
          </div>

          <form onSubmit={onSubmit} className="mt-4 pt-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  isAuthenticated ? "Ask the agent…" : "Connect wallet and sign in to chat"
                }
                disabled={!token || busy}
                className="flex-1 bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!token || busy || !input.trim()}
                className="bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
        </Panel>

        <div className="space-y-6">
          <Panel title="Quick prompts">
            <div className="flex flex-col gap-2">
              {config.examplePrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={!token || busy}
                  onClick={() => void runCommand(prompt)}
                  className="bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground transition hover:bg-surface hover:text-foreground disabled:opacity-40"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </Panel>

          {actions.length > 0 && (
            <Panel title="Tool results">
              <div className="max-h-80 space-y-3 overflow-y-auto font-mono text-[11px]">
                {actions.map((action, idx) => (
                  <div key={`${action.tool}-${idx}`} className="bg-surface/30 p-3">
                    <div className="mb-1 text-signal">{action.tool}</div>
                    <pre className="whitespace-pre-wrap break-all text-muted-foreground">
                      {action.result}
                    </pre>
                  </div>
                ))}
                <div ref={actionsEndRef} />
              </div>
            </Panel>
          )}
        </div>
      </div>

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to start chatting.
        </div>
      )}
    </div>
  );
}
