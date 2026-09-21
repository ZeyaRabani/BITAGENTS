"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useConnection, useWallet } from "@solana/wallet-adapter-react";
import { LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { Panel } from "@/components/AppShell";
import { AgentCard } from "@/components/agents/AgentCard";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import { explorerUrlForSignature } from "@/lib/dcaActionResults";
import {
  fetchPublicLaunchedAgent,
  subscribeToAgent,
  type LaunchedAgent,
} from "@/lib/launchAgentClient";
import { mapLaunchedToMarketplaceAgent } from "@/lib/launchMarketplace";
import { LAUNCH_MODULES } from "@/lib/launchAgentModules";

export function LaunchedAgentDetail({ agentId }: { agentId: string }) {
  const { connection } = useConnection();
  const { publicKey, connected, sendTransaction } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();

  const [agent, setAgent] = useState<LaunchedAgent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [buyBusy, setBuyBusy] = useState(false);
  const [buyPhase, setBuyPhase] = useState<string | null>(null);
  const [buyError, setBuyError] = useState<string | null>(null);
  const [buySuccess, setBuySuccess] = useState<string | null>(null);
  const [lastTx, setLastTx] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchPublicLaunchedAgent(agentId).then((row) => {
      if (cancelled) return;
      if (!row) {
        setError("Agent not found or not publicly listed.");
        setAgent(null);
      } else {
        setAgent(row);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  async function onSubscribe() {
    setBuyError(null);
    setBuySuccess(null);
    setLastTx(null);

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
    const price = agent.price_per_month_sol;
    if (price == null || !(price > 0)) {
      setBuyError("This agent has no monthly price.");
      return;
    }

    setBuyBusy(true);
    setBuyPhase("Preparing payment…");
    try {
      const sellerPk = new PublicKey(agent.user_wallet);
      const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash("confirmed");
      const tx = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: sellerPk,
          lamports: Math.round(price * LAMPORTS_PER_SOL),
        })
      );
      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;

      setBuyPhase("Approve in wallet…");
      const signature = await sendTransaction(tx, connection);
      setLastTx(signature);

      setBuyPhase("Confirming on-chain…");
      await connection.confirmTransaction(
        { signature, blockhash, lastValidBlockHeight },
        "confirmed"
      );

      setBuyPhase("Recording subscription…");
      const result = await subscribeToAgent(agent.id, signature, token);
      setBuySuccess(result.message ?? `Subscribed to ${agent.name}.`);
    } catch (err) {
      setBuyError(err instanceof Error ? err.message : "Subscribe failed");
    } finally {
      setBuyBusy(false);
      setBuyPhase(null);
    }
  }

  if (loading) {
    return (
      <div className="border border-grid bg-surface/40 px-4 py-6 font-mono text-xs text-muted-foreground">
        Loading agent…
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div className="space-y-4">
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          {error ?? "Agent not found."}
        </div>
        <Link href="/agents" className="font-mono text-xs text-signal underline">
          ← Back to marketplace
        </Link>
      </div>
    );
  }

  const card = mapLaunchedToMarketplaceAgent(agent);
  const moduleNames = LAUNCH_MODULES.filter((m) => agent.modules.includes(m.id)).map(
    (m) => m.name
  );
  const price = agent.price_per_month_sol;
  const isOwner = Boolean(publicKey && publicKey.toBase58() === agent.user_wallet);

  return (
    <div className="space-y-6">
      <Link
        href="/agents"
        className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition hover:text-signal"
      >
        ← Marketplace
      </Link>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,340px)_1fr]">
        <AgentCard agent={card} />

        <div className="space-y-4">
          <Panel title="About">
            <p className="text-sm leading-relaxed text-muted-foreground">
              {agent.description || "No description provided."}
            </p>
            <div className="mt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {agent.visibility}
              {price != null ? ` · ${price} SOL / month` : ""}
            </div>
          </Panel>

          <Panel title="Subscribe">
            <p className="text-sm text-muted-foreground">
              Pay the monthly price in SOL to the creator. Access is recorded for 30 days and shows
              under Dashboard → Agents you bought.
            </p>
            {authError && (
              <p className="mt-3 font-mono text-[11px] text-warn">Wallet sign-in: {authError}</p>
            )}
            {buyPhase && (
              <p className="mt-3 font-mono text-[11px] text-muted-foreground">{buyPhase}</p>
            )}
            {buyError && (
              <p className="mt-3 font-mono text-[11px] text-warn">{buyError}</p>
            )}
            {buySuccess && (
              <div className="mt-3 border border-signal/40 bg-signal/10 px-3 py-2 font-mono text-[11px] text-signal">
                {buySuccess}
                {lastTx && (
                  <a
                    href={explorerUrlForSignature(lastTx)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block break-all underline"
                  >
                    {lastTx} ↗
                  </a>
                )}
                <Link href="/agents/dashboard" className="mt-2 block underline">
                  Open dashboard →
                </Link>
              </div>
            )}
            <button
              type="button"
              disabled={
                buyBusy ||
                authBusy ||
                isOwner ||
                !price ||
                price <= 0 ||
                !connected
              }
              onClick={() => void onSubscribe()}
              className="mt-4 bg-signal px-5 py-3 font-mono text-xs font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {buyBusy
                ? "Subscribing…"
                : isOwner
                  ? "Your listing"
                  : !connected
                    ? "Connect wallet"
                    : !isAuthenticated
                      ? "Sign in required"
                      : `Subscribe · ${price} SOL / mo`}
            </button>
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
        </div>
      </div>
    </div>
  );
}
