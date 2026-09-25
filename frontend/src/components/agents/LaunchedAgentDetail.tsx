"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { AppShell, Panel } from "@/components/AppShell";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import {
  chatWithLaunchedAgent,
  fetchLaunchedAgent,
  fetchPublicLaunchedAgent,
  subscribeToAgent,
  type LaunchedAgent,
} from "@/lib/launchAgentClient";
import { LAUNCH_MODULES } from "@/lib/launchAgentModules";

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

const QUICK_PROMPTS = [
  "What can you do for me?",
  "Give me a live update in your scope.",
  "Summarize the latest news you can see.",
];

export function LaunchedAgentDetail({ agentId }: { agentId: string }) {
  const { connection } = useConnection();
  const { publicKey, connected, sendTransaction } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();

  const [agent, setAgent] = useState<LaunchedAgent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [accessAllowed, setAccessAllowed] = useState(false);
  const [accessReason, setAccessReason] = useState<string>("");

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string>();
  const [chatBusy, setChatBusy] = useState(false);

  const [buyBusy, setBuyBusy] = useState(false);
  const [buyError, setBuyError] = useState<string | null>(null);
  const [buySuccess, setBuySuccess] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const freeUse = agent?.mode === "development" || agent?.payment_required === false;
  const isOwner = Boolean(publicKey && agent && publicKey.toBase58() === agent.user_wallet);
  const canChat = Boolean(isAuthenticated && (accessAllowed || freeUse || isOwner));

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const pub = await fetchPublicLaunchedAgent(agentId);
        if (cancelled) return;
        if (pub) {
          setAgent(pub);
          if (pub.mode === "development" || pub.payment_required === false) {
            setAccessAllowed(true);
            setAccessReason("development");
          }
        }

        if (token) {
          try {
            const owned = await fetchLaunchedAgent(agentId, token);
            if (cancelled) return;
            setAgent(owned.agent);
            if (owned.access?.allowed) {
              setAccessAllowed(true);
              setAccessReason(owned.access.reason ?? "allowed");
            } else if (
              owned.agent.mode === "development" ||
              owned.agent.payment_required === false
            ) {
              setAccessAllowed(true);
              setAccessReason("development");
            }
          } catch (err) {
            if (!pub && !cancelled) {
              setError(err instanceof Error ? err.message : "Agent not found.");
              setAgent(null);
            }
          }
        } else if (!pub) {
          setError("Agent not found or not publicly listed.");
          setAgent(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [agentId, token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatBusy]);

  async function onSubscribe() {
    setBuyError(null);
    setBuySuccess(null);
    if (!agent) return;
    if (!connected || !publicKey) {
      setBuyError("Connect your wallet first.");
      return;
    }
    if (!isAuthenticated || !token) {
      setBuyError("Approve the wallet sign-in message before subscribing.");
      return;
    }
    if (publicKey.toBase58() === agent.user_wallet) {
      setBuyError("You cannot subscribe to your own agent.");
      return;
    }

    const skipPay = agent.mode === "development" || agent.payment_required === false;
    const price = agent.price_per_month_sol ?? 0;
    setBuyBusy(true);
    try {
      let signature = "";
      if (!skipPay) {
        if (!(price > 0)) {
          throw new Error("This agent has no monthly price.");
        }
        const rate = agent.platform_fee_rate ?? 0.1;
        const creatorDest = agent.creator_payout_wallet || agent.user_wallet;
        const platformDest = agent.platform_fee_wallet;
        const creatorLamports = Math.round(price * (1 - rate) * LAMPORTS_PER_SOL);
        const platformLamports = Math.round(price * rate * LAMPORTS_PER_SOL);
        const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
        const tx = new Transaction();
        tx.add(
          SystemProgram.transfer({
            fromPubkey: publicKey,
            toPubkey: new PublicKey(creatorDest),
            lamports: creatorLamports,
          })
        );
        if (platformDest && platformLamports > 0) {
          tx.add(
            SystemProgram.transfer({
              fromPubkey: publicKey,
              toPubkey: new PublicKey(platformDest),
              lamports: platformLamports,
            })
          );
        }
        tx.recentBlockhash = blockhash;
        tx.feePayer = publicKey;
        signature = await sendTransaction(tx, connection);
        await connection.confirmTransaction(
          { signature, blockhash, lastValidBlockHeight },
          "confirmed"
        );
      }
      const result = await subscribeToAgent(agent.id, signature, token);
      setBuySuccess(result.message ?? `Subscribed to ${agent.name}.`);
      setAccessAllowed(true);
      setAccessReason(skipPay ? "development" : "subscribed");
    } catch (err) {
      setBuyError(err instanceof Error ? err.message : "Subscribe failed");
    } finally {
      setBuyBusy(false);
    }
  }

  async function runCommand(text: string) {
    if (!token || !text.trim() || !agent) return;
    setChatBusy(true);
    setError(null);
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", content: text.trim() }]);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const res = await chatWithLaunchedAgent(
        agent.id,
        { message: text.trim(), session_id: sessionId, history },
        token
      );
      setSessionId(res.session_id);
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: "assistant", content: res.reply },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setError(msg);
      setMessages((prev) => [...prev, { id: `e-${Date.now()}`, role: "assistant", content: msg }]);
    } finally {
      setChatBusy(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    void runCommand(text);
  }

  if (loading) {
    return (
      <AppShell title="Community agent" subtitle="Loading this marketplace agent…">
        <div className="border border-grid bg-surface/40 px-4 py-6 font-mono text-xs text-muted-foreground">
          Loading agent…
        </div>
      </AppShell>
    );
  }

  if (error && !agent) {
    return (
      <AppShell title="Community agent" subtitle="This listing is unavailable.">
        <div className="space-y-4">
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            {error}
          </div>
          <Link href="/agents" className="font-mono text-xs text-signal underline">
            Back to marketplace
          </Link>
        </div>
      </AppShell>
    );
  }

  if (!agent) return null;

  const moduleNames = LAUNCH_MODULES.filter((m) => agent.modules.includes(m.id)).map((m) => m.name);
  const price = agent.price_per_month_sol;
  const rate = agent.platform_fee_rate ?? 0.1;
  const subtitle = agent.description || agent.task;

  return (
    <AppShell title={agent.name} subtitle={subtitle}>
      <div className="space-y-6">
        <div className="border border-grid bg-surface/40 px-4 py-4">
          <p className="text-sm leading-relaxed text-muted-foreground">
            {agent.description || agent.task} Connect your wallet
            {freeUse ? " (free in development)" : ""} to chat with this agent.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          <span className="inline-flex items-center gap-2 text-signal">
            <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal" />
            Community
          </span>
          <span>·</span>
          <span>{price != null ? `${price} SOL / month` : "No monthly price"}</span>
          {freeUse ? (
            <>
              <span>·</span>
              <span className="text-signal">Free · development</span>
            </>
          ) : (
            <>
              <span>·</span>
              <span>
                {Math.round(rate * 100)}% platform · {Math.round((1 - rate) * 100)}% creator
              </span>
            </>
          )}
          {isOwner || accessReason === "owner" ? (
            <>
              <span>·</span>
              <span className="text-signal">Your agent</span>
            </>
          ) : null}
        </div>

        {error && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            {error}
          </div>
        )}

        {authError && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            Wallet sign-in: {authError}
          </div>
        )}

        {publicKey && authBusy && (
          <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
            Approve the wallet sign-in message to use {agent.name}
            {freeUse ? " (free)." : "."}
          </div>
        )}

        {!publicKey && (
          <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
            Connect your wallet to sign in and chat.
          </div>
        )}

        {connected && !isAuthenticated && !authBusy && (
          <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
            Wallet connected - approve the sign-in prompt, or reconnect if it was dismissed.
          </div>
        )}

        {!canChat && isAuthenticated && !isOwner && (
          <Panel title="Subscribe">
            <p className="text-sm text-muted-foreground">
              {freeUse
                ? "Development mode: start this agent at 0 SOL."
                : `Pay ${price ?? 0} SOL for 30 days. ${Math.round((1 - rate) * 100)}% goes to the creator Circle wallet so they can claim later. The platform keeps ${Math.round(rate * 100)}%.`}
            </p>
            {buyError && <p className="mt-3 font-mono text-[11px] text-warn">{buyError}</p>}
            {buySuccess && <p className="mt-3 font-mono text-[11px] text-signal">{buySuccess}</p>}
            <button
              type="button"
              disabled={buyBusy || authBusy || !connected}
              onClick={() => void onSubscribe()}
              className="mt-4 bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {buyBusy
                ? "Starting…"
                : !connected
                  ? "Connect wallet"
                  : freeUse
                    ? "Use agent · 0 SOL"
                    : `Subscribe · ${price} SOL / mo`}
            </button>
          </Panel>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          <Panel title={agent.name} className="lg:col-span-2">
            <div className="flex max-h-105 flex-col gap-4 overflow-y-auto pr-1">
              {messages.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  {canChat
                    ? "Try a prompt or ask a question in natural language."
                    : freeUse
                      ? "Connect your wallet and sign in to chat (free in development)."
                      : "Subscribe to chat with this agent."}
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
                    {msg.role === "user" ? "You" : agent.name}
                  </div>
                  <div className="space-y-1">{formatReply(msg.content)}</div>
                </div>
              ))}
              {chatBusy && (
                <div className="animate-pulse font-mono text-xs text-muted-foreground">
                  Thinking…
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <form onSubmit={onSubmit} className="mt-4 border-t border-grid pt-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    canChat
                      ? "Ask the agent…"
                      : freeUse
                        ? "Connect wallet and sign in to chat"
                        : "Subscribe to chat"
                  }
                  disabled={!canChat || chatBusy}
                  className="flex-1 border border-grid bg-background px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!canChat || chatBusy || !input.trim()}
                  className="border border-signal bg-signal/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-signal disabled:opacity-40"
                >
                  Send
                </button>
              </div>
            </form>
          </Panel>

          <div className="space-y-6">
            <Panel title="Quick prompts">
              <div className="flex flex-col gap-2">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={!canChat || chatBusy}
                    onClick={() => void runCommand(prompt)}
                    className="border border-grid bg-surface/40 px-3 py-2 text-left font-mono text-xs text-muted-foreground transition hover:border-signal/40 hover:text-foreground disabled:opacity-40"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </Panel>
            <Panel title="Agent task">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {agent.task}
              </p>
            </Panel>
            <Panel title="Modules">
              {moduleNames.length === 0 ? (
                <p className="text-sm text-muted-foreground">No modules listed.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {moduleNames.map((label) => (
                    <span
                      key={label}
                      className="border border-grid px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              )}
            </Panel>
            {isOwner && (
              <Panel title="Owner">
                <Link
                  href={`/agents/launch?edit=${agent.id}`}
                  className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline"
                >
                  Edit / relaunch
                </Link>
              </Panel>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
