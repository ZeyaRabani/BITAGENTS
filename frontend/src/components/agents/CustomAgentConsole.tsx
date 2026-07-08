"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel } from "@/components/AppShell";
import { useCustomAgentWalletAuth } from "@/hooks/useCustomAgentWalletAuth";
import {
  getCustomAgent,
  sendCustomAgentMessage,
  type CustomAgent,
} from "@/lib/customAgentClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <span key={i} className="block">
      {line}
    </span>
  ));
}

export function CustomAgentConsole({ agentId }: { agentId: string }) {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useCustomAgentWalletAuth();
  const [agent, setAgent] = useState<CustomAgent | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    void getCustomAgent(agentId, token)
      .then(setAgent)
      .catch((err) => setAgentError(err instanceof Error ? err.message : "Failed to load agent"));
  }, [agentId, token]);

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
      const res = await sendCustomAgentMessage(agentId, text.trim(), token, history);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
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
      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{error}</div>
      )}
      {agentError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">{agentError}</div>
      )}
      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}
      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to chat with this agent.
        </div>
      )}
      {!publicKey && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet to sign in and chat with this agent.
        </div>
      )}

      <Panel title={agent?.name ?? "Custom agent"}>
        {agent?.description && (
          <p className="mb-4 text-sm text-muted-foreground">{agent.description}</p>
        )}
        <div className="flex max-h-[420px] flex-col gap-4 overflow-y-auto pr-1">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Say hello to start chatting with this agent.
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
                {msg.role === "user" ? "You" : agent?.name ?? "Agent"}
              </div>
              <div className="space-y-1">{formatReply(msg.content)}</div>
            </div>
          ))}
          {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Thinking…</div>}
          <div ref={chatEndRef} />
        </div>

        <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy || !token}
              placeholder={token ? "Send a message..." : "Sign in with wallet to chat"}
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
      </Panel>

      {publicKey && !isAuthenticated && !authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in prompt to start chatting.
        </div>
      )}
    </div>
  );
}
