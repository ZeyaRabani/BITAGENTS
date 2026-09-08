"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import { Panel } from "@/components/AppShell";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { sendBuilderMessage } from "@/lib/launchpadBuilderClient";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const STARTER_PROMPTS = [
  "I want an agent that watches whale wallets and alerts me on big moves",
  "I want an agent that researches a token before I buy it",
  "I want an agent that DCAs into SOL every day automatically",
];

function formatReply(text: string) {
  return text.split("\n").map((line, i) => (
    <p key={i} className={line.trim() === "" ? "h-2" : undefined}>
      {line}
    </p>
  ));
}

export function AgentBuilderChat() {
  const router = useRouter();
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justLaunched, setJustLaunched] = useState(false);
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
      const res = await sendBuilderMessage(text.trim(), token, sessionId);
      setSessionId(res.session_id);
      setMessages((prev) => [...prev, { id: `a-${Date.now()}`, role: "assistant", content: res.reply }]);
      const launched = res.actions?.some(
        (a) => a.tool === "finalize_and_launch" && a.result?.includes('"ok": true')
      );
      if (launched) {
        setJustLaunched(true);
        setTimeout(() => router.push("/launch"), 2500);
      }
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
    void runMessage(text);
  }

  return (
    <div className="space-y-6">
      {!publicKey && (
        <div className="flex flex-col items-start gap-3 border border-grid bg-surface/40 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">Connect your wallet to start building an agent.</p>
          <WalletMultiButton className="wallet-adapter-button-trigger!" />
        </div>
      )}

      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {publicKey && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to continue.
        </div>
      )}

      {justLaunched && (
        <div className="border border-signal bg-surface/60 px-4 py-3 font-mono text-xs text-signal">
          Agent launched — entering its 24h private testing window. Redirecting to the launchpad…
        </div>
      )}

      <Panel title="Build your agent">
        <div className="flex max-h-125 flex-col gap-4 overflow-y-auto pr-1">
          {messages.length === 0 && (
            <div className="space-y-3">
              <p className="text-sm leading-relaxed text-muted-foreground">
                Describe what you want your agent to do — in your own words. I'll ask follow-up
                questions and write the actual instructions it runs on.
              </p>
              <div className="flex flex-col gap-2">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={!token || busy}
                    onClick={() => void runMessage(prompt)}
                    className="border border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground transition hover:border-signal/40 hover:text-foreground disabled:opacity-40"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
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
                {msg.role === "user" ? "You" : "Agent Builder"}
              </div>
              <div className="space-y-1">{formatReply(msg.content)}</div>
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
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isAuthenticated ? "Tell it what you want to build…" : "Connect wallet and sign in to chat"}
              disabled={!token || busy}
              className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={!token || busy || !input.trim()}
              className="border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
