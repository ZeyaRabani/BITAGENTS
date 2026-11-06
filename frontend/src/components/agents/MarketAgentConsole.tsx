"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Panel } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { LegalSignInNotice } from "@/components/legal/LegalSignInNotice";
import {
  explorerUrlForSignature,
  findLatestConfirmationRequired,
} from "@/lib/dcaActionResults";
import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { useWallet } from "@solana/wallet-adapter-react";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  errors?: string[];
};

type AgentWallet = {
  agent_wallet?: string | null;
  sol_balance?: number | null;
  balance_error?: string | null;
  cluster?: string;
};

export function MarketAgentConsole({
  slug,
  title,
  intro,
  prompts,
}: {
  slug: "hedge-fund" | "sniper";
  title: string;
  intro: string;
  prompts: string[];
}) {
  const { publicKey } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useDcaWalletAuth();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: "intro", role: "assistant", content: intro },
  ]);
  const [actions, setActions] = useState<AgentAction[]>([]);
  const [wallet, setWallet] = useState<AgentWallet | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!token) {
      setWallet(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const res = await fetch(`/api/agents/${slug}/wallet`, {
        cache: "no-store",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok || cancelled) return;
      const data = (await res.json()) as AgentWallet;
      if (!cancelled) setWallet(data);
    })();
    return () => {
      cancelled = true;
    };
  }, [slug, token, actions.length]);

  async function runCommand(command: string) {
    const text = command.trim();
    if (!text || !token) return;
    setBusy(true);
    setError(null);
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", content: text },
    ]);
    try {
      const res = await fetch(`/api/agents/${slug}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const data = (await res.json()) as {
        reply?: string;
        session_id?: string;
        actions?: { tool: string; args: Record<string, unknown>; result: string }[];
        detail?: string;
        error?: string;
      };
      if (!res.ok) {
        throw new Error(data.detail || data.error || "Request failed");
      }
      if (data.session_id) setSessionId(data.session_id);
      const mapped = mapApiActions(data.actions ?? []);
      setActions((current) => [...current, ...mapped]);
      const errors = mapped.map((item) => item.error).filter((item): item is string => Boolean(item));
      setMessages((current) => [
        ...current,
        {
          id: `agent-${Date.now()}`,
          role: "assistant",
          content: data.reply || "No reply.",
          errors,
        },
      ]);
      const pending = findLatestConfirmationRequired(data.actions ?? []);
      if (pending) {
        setConfirmMessage(pending.message);
        setConfirmOpen(true);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      setError(message);
    } finally {
      setBusy(false);
      setInput("");
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void runCommand(input);
  }

  const address = wallet?.agent_wallet;
  const cluster = wallet?.cluster || "mainnet";

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
          Approve the wallet sign-in message to authenticate.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title={`Command ${title}`} className="lg:col-span-2">
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
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.errors && msg.errors.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-warn/30 pt-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-warn">Error</div>
                    {msg.errors.map((err) => (
                      <p key={err} className="font-mono text-[11px] leading-relaxed text-warn">
                        {err}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && (
              <div className="animate-pulse font-mono text-xs text-muted-foreground">Working…</div>
            )}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={busy || !token}
                placeholder={token ? "Ask for a swap" : "Sign in with wallet to chat"}
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
            {prompts.map((prompt) => (
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
                Swap quotes, Aomi checks, and signatures show up here.
              </p>
            )}
            {actions.map((act, index) => (
              <div key={`${act.id}-${index}`} className="border border-grid px-3 py-2">
                <div className="uppercase tracking-[0.14em] text-signal">
                  {act.status === "error" ? "error" : "done"} {act.tool}
                </div>
                {act.error && <p className="mt-1 text-warn">{act.error}</p>}
                {act.transactions.map((tx) => (
                  <a
                    key={tx.signature}
                    href={tx.explorerUrl || explorerUrlForSignature(tx.signature, cluster)}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block truncate text-foreground underline"
                  >
                    {tx.signature}
                  </a>
                ))}
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Panel title="AI Agent wallet">
        {!isAuthenticated && (
          <p className="font-mono text-xs text-muted-foreground">
            Sign in with your wallet. This agent then creates its own Circle address.
          </p>
        )}
        {address && (
          <div className="space-y-2 font-mono text-xs">
            <p className="break-all text-foreground">{address}</p>
            <p className="text-muted-foreground">
              SOL balance: {wallet?.sol_balance == null ? "-" : wallet.sol_balance.toFixed(6)}
            </p>
            {wallet?.balance_error && <p className="text-warn">{wallet.balance_error}</p>}
            <p className="text-muted-foreground">
              Send SOL to this address to fund the agent. Swaps leave only after Aomi simulates them.
            </p>
          </div>
        )}
      </Panel>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Confirm ${title}`}
        description={<p className="whitespace-pre-wrap">{confirmMessage}</p>}
        confirmLabel="Yes, proceed"
        cancelLabel="No, cancel"
        busy={busy}
        onCancel={() => {
          setConfirmOpen(false);
          void runCommand("no, cancel");
        }}
        onConfirm={() => {
          setConfirmOpen(false);
          void runCommand("yes, confirm");
        }}
      />
      <LegalSignInNotice />
    </div>
  );
}
