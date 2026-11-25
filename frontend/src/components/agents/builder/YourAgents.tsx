"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { useWallet } from "@solana/wallet-adapter-react";
import { BTN_GHOST, Notice, StatusBadge } from "@/components/agents/builder/BuilderUi";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { getStoredDcaAuth } from "@/lib/dcaAuthClient";
import { builderApi, errorText, isAbort, type BuilderAgent } from "@/lib/builderClient";

const HEADING = "font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground";

export function CreateAgentCard() {
  return (
    <Link href="/agents/create" className="block h-full">
      <article className="group flex h-full flex-col border border-dashed border-signal/50 bg-card p-5 transition hover:border-signal">
        <h3 className="font-display text-lg font-bold transition group-hover:text-signal">
          Create your strategy
        </h3>
        <p className="mt-3 text-sm leading-snug text-muted-foreground">
          Describe a strategy in plain words. The builder composes the spec, deploys it to Aomi
          and gives you a console for it.
        </p>
        <div className="mt-auto pt-5">
          <span className="inline-flex w-full items-center justify-between border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
            Start building
            <ArrowRight size={14} />
          </span>
        </div>
      </article>
    </Link>
  );
}

/**
 * The signed-in wallet's built agents. Renders nothing until a wallet is
 * connected. The marketplace does not ask for a signature on its own: the
 * list loads when a wallet session already exists, or after the user asks.
 */
export function YourAgents() {
  const { publicKey } = useWallet();
  const wallet = publicKey?.toBase58() ?? null;
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    setRequested(false);
  }, [wallet]);

  if (!wallet) return null;
  const hasSession = Boolean(getStoredDcaAuth(wallet));

  return (
    <section className="mt-10">
      <div className="mb-4">
        <h2 className={HEADING}>Your strategies</h2>
      </div>
      {hasSession || requested ? (
        <YourAgentsList />
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-xs text-muted-foreground">
            Sign in with your wallet to list the strategies you built.
          </span>
          <button type="button" onClick={() => setRequested(true)} className={BTN_GHOST}>
            Sign in
          </button>
        </div>
      )}
    </section>
  );
}

export function YourAgentsList() {
  const { token, busy: authBusy, error: authError } = useDcaWalletAuth();
  const [agents, setAgents] = useState<BuilderAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAgents(null);
    setError(null);
    if (!token) return;
    const controller = new AbortController();
    builderApi
      .listMine(token, controller.signal)
      .then((data) => setAgents(data.agents ?? []))
      .catch((err) => {
        if (!isAbort(err)) setError(errorText(err));
      });
    return () => controller.abort();
  }, [token]);

  if (authError) return <Notice tone="warn">Wallet sign-in: {authError}</Notice>;
  if (!token) {
    return (
      <p className="font-mono text-xs text-muted-foreground">
        {authBusy ? "Approve the wallet sign-in message to authenticate." : "Not signed in."}
      </p>
    );
  }
  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!agents) return <p className="font-mono text-xs text-muted-foreground">Loading your strategies…</p>;
  if (agents.length === 0) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
        This wallet has not built an agent yet.
      </p>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <Link key={agent.id} href={`/agents/custom/${agent.id}`} className="block h-full">
          <article className="group flex h-full flex-col border border-grid bg-card p-5 transition hover:border-signal">
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-display text-lg font-bold transition group-hover:text-signal">
                {agent.spec.name}
              </h3>
              <StatusBadge status={agent.build_status} />
            </div>
            <p className="mt-3 text-sm leading-snug text-muted-foreground">{agent.spec.description}</p>
            <div className="mt-5 border-t border-grid pt-4">
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                Template
              </div>
              <div className="mt-1 font-mono text-xs text-foreground">{agent.spec.strategy.template}</div>
            </div>
            <div className="mt-auto pt-5">
              <span className="inline-flex w-full items-center justify-between border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
                Open console
                <ArrowRight size={14} />
              </span>
            </div>
          </article>
        </Link>
      ))}
    </div>
  );
}
