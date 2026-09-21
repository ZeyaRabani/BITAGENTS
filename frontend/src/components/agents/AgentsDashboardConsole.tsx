"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel, Stat } from "@/components/AppShell";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import {
  fetchLaunchDashboard,
  type AgentSubscription,
  type LaunchDashboard,
  type LaunchedAgent,
} from "@/lib/launchAgentClient";

function formatExpiry(value?: string) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function OwnedAgentRow({ agent }: { agent: LaunchedAgent }) {
  const href =
    agent.visibility === "public"
      ? `/agents/launched/${agent.id}`
      : "/agents/launch";

  return (
    <div className="border border-grid bg-surface/30 px-3 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link href={href} className="font-mono text-sm font-semibold text-foreground hover:text-signal">
          {agent.name}
        </Link>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {agent.visibility}
          {agent.price_per_month_sol != null ? ` · ${agent.price_per_month_sol} SOL/mo` : ""}
          {agent.visibility === "public"
            ? ` · ${agent.active_subscribers ?? 0} subscribers`
            : ""}
        </span>
      </div>
      {agent.description && (
        <p className="mt-1 text-xs text-muted-foreground">{agent.description}</p>
      )}
      <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{agent.task}</p>
    </div>
  );
}

function SubscriptionRow({
  sub,
  mode,
}: {
  sub: AgentSubscription;
  mode: "bought" | "sale";
}) {
  const name = sub.agent_name || sub.agent_id;
  const active =
    sub.status === "active" &&
    (!sub.expires_at || new Date(sub.expires_at).getTime() > Date.now());

  return (
    <div className="border border-grid bg-surface/30 px-3 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link
          href={`/agents/launched/${sub.agent_id}`}
          className="font-mono text-sm font-semibold text-foreground hover:text-signal"
        >
          {name}
        </Link>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {active ? "active" : sub.status} · {sub.price_sol} SOL
        </span>
      </div>
      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        {mode === "bought" ? "Seller" : "Buyer"}:{" "}
        {(mode === "bought" ? sub.seller_wallet : sub.buyer_wallet).slice(0, 4)}…
        {(mode === "bought" ? sub.seller_wallet : sub.buyer_wallet).slice(-4)}
        {" · "}expires {formatExpiry(sub.expires_at)}
      </p>
      {sub.explorer_url && (
        <a
          href={sub.explorer_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block font-mono text-[10px] text-signal hover:underline"
        >
          Payment tx ↗
        </a>
      )}
    </div>
  );
}

export function AgentsDashboardConsole() {
  const { publicKey, connected } = useWallet();
  const { token, busy: authBusy, error: authError, isAuthenticated } = useKickstartWalletAuth();
  const [data, setData] = useState<LaunchDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!token) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await fetchLaunchDashboard(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="space-y-6">
      <div className="border border-grid bg-surface/40 px-4 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Track agents you launched for sale, private agents you keep for yourself, monthly
          subscriptions you bought, and sales from buyers.
        </p>
      </div>

      {authError && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet sign-in: {authError}
        </div>
      )}

      {!connected && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Connect your wallet in the navbar to view your dashboard.
        </div>
      )}

      {connected && authBusy && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Approve the wallet sign-in message to load your agents.
        </div>
      )}

      {isAuthenticated && (
        <div className="border border-signal/30 bg-signal/5 px-4 py-3 font-mono text-[11px] text-signal">
          Signed in as {publicKey?.toBase58().slice(0, 4)}…{publicKey?.toBase58().slice(-4)}
          <button
            type="button"
            onClick={() => void reload()}
            className="ml-3 underline hover:text-foreground"
          >
            Refresh
          </button>
        </div>
      )}

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          {error}
        </div>
      )}

      {isAuthenticated && data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Listed for sale" value={String(data.counts.listed_for_sale)} accent="signal" />
            <Stat label="Private agents" value={String(data.counts.private_agents)} />
            <Stat label="Bought" value={String(data.counts.bought)} accent="signal" />
            <Stat label="Sales" value={String(data.counts.sales)} />
          </div>

          <Panel
            title="Agents you put up for sale"
            action={
              <Link
                href="/agents/launch"
                className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline"
              >
                Launch new
              </Link>
            }
          >
            {loading && !data.listed_for_sale.length ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : data.listed_for_sale.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No public listings yet. Launch an agent as public with a monthly price to sell
                access.
              </p>
            ) : (
              <div className="space-y-3">
                {data.listed_for_sale.map((agent) => (
                  <OwnedAgentRow key={agent.id} agent={agent} />
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Private agents you launched">
            {data.private_agents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No private agents yet.</p>
            ) : (
              <div className="space-y-3">
                {data.private_agents.map((agent) => (
                  <OwnedAgentRow key={agent.id} agent={agent} />
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Agents you bought">
            {data.bought.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No subscriptions yet. Open a community agent on the marketplace and subscribe for
                one month.
              </p>
            ) : (
              <div className="space-y-3">
                {data.bought.map((sub) => (
                  <SubscriptionRow key={sub.id} sub={sub} mode="bought" />
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Sales to buyers">
            {data.sales.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No buyers yet. When someone subscribes to your public agent, it shows up here.
              </p>
            ) : (
              <div className="space-y-3">
                {data.sales.map((sub) => (
                  <SubscriptionRow key={sub.id} sub={sub} mode="sale" />
                ))}
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
