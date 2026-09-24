"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import type { LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

async function sendCustomAgentMessage(
  agentId: string,
  message: string,
  authToken: string,
  sessionId?: string
) {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? data.error ?? "Request failed");
  return data as { reply: string; session_id: string; actions: unknown[] };
}

export function CustomAgentChat({ agent }: { agent: LaunchedAgentRecord }) {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError } = useDcaWalletAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function runMessage(text: string) {
    if (!token || !text.trim()) return;
    setBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text.trim() }]);
    try {
      const res = await sendCustomAgentMessage(agent.id, text.trim(), token, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", content: res.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runMessage(text);
  }

  return (
    <Panel title={`Talk to ${agent.name ?? "this agent"}`}>
      {!publicKey ? (
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">Connect your wallet to talk to this agent.</p>
          <WalletMultiButton className="wallet-adapter-button-trigger!" />
        </div>
      ) : authError ? (
        <p className="font-mono text-xs text-warn">Wallet sign-in: {authError}</p>
      ) : authBusy ? (
        <p className="font-mono text-xs text-muted-foreground">Approve the wallet sign-in message to continue.</p>
      ) : (
        <>
          <div className="flex max-h-100 flex-col gap-4 overflow-y-auto pr-1">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Ask it anything within what it's set up to do — its system prompt shapes how it responds.
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
                  {msg.role === "user" ? "You" : agent.name ?? "Agent"}
                </div>
                <div>{msg.content}</div>
              </div>
            ))}
            {busy && <div className="animate-pulse font-mono text-xs text-muted-foreground">Thinking…</div>}
            <div ref={chatEndRef} />
          </div>

          {error && (
            <div className="mt-4 border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    onSubmit(e);
                  }
                }}
                placeholder="Message this agent… (Shift+Enter for a new line)"
                disabled={busy}
                rows={1}
                className="max-h-40 min-h-[42px] flex-1 resize-y border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="self-start border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </form>
        </>
      )}
    </Panel>
  );
}
