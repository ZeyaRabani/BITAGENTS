"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useWallet } from "@solana/wallet-adapter-react";
import { Panel, Stat } from "@/components/AppShell";
import { useKickstartWalletAuth } from "@/hooks/useKickstartWalletAuth";
import {
  fetchLaunchDashboard,
  listLaunchedAgents,
  type AgentSubscription,
  type LaunchDashboard,
  type LaunchedAgent,
} from "@/lib/launchAgentClient";

function emptyDashboard(): LaunchDashboard {
  return {
    listed_for_sale: [],
    private_agents: [],
    bought: [],
    sales: [],
    counts: {
      listed_for_sale: 0,
      private_agents: 0,
      bought: 0,
      sales: 0,
    },
  };
}

function formatExpiry(value?: string) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function OwnedAgentRow({ agent }: { agent: LaunchedAgent }) {
  return (
    <div className="border border-grid bg-surface/30 px-3 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link
          href={`/agents/launched/${agent.id}`}
          className="font-mono text-sm font-semibold text-foreground hover:text-signal"
        >
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
      <div className="mt-3 flex flex-wrap gap-3">
        <Link
          href={`/agents/launch?edit=${agent.id}`}
          className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline"
        >
          Edit / relaunch
        </Link>
        <Link
          href={`/agents/launched/${agent.id}`}
          className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground hover:text-signal"
        >
          Open agent
        </Link>
      </div>
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
  const { connected } = useWallet();
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
      const dash = await fetchLaunchDashboard(token);
      setData({
        listed_for_sale: dash.listed_for_sale ?? [],
        private_agents: dash.private_agents ?? [],
        bought: dash.bought ?? [],
        sales: dash.sales ?? [],
        counts: {
          listed_for_sale: dash.counts?.listed_for_sale ?? dash.listed_for_sale?.length ?? 0,
          private_agents: dash.counts?.private_agents ?? dash.private_agents?.length ?? 0,
          bought: dash.counts?.bought ?? dash.bought?.length ?? 0,
          sales: dash.counts?.sales ?? dash.sales?.length ?? 0,
        },
      });
    } catch (err) {
      // Fallback: still show owned agents if dashboard endpoint fails.
      try {
        const owned = await listLaunchedAgents(token);
        const listed = owned.filter((a) => a.visibility === "public");
        const privateAgents = owned.filter((a) => a.visibility !== "public");
        setData({
          listed_for_sale: listed,
          private_agents: privateAgents,
          bought: [],
          sales: [],
          counts: {
            listed_for_sale: listed.length,
            private_agents: privateAgents.length,
            bought: 0,
            sales: 0,
          },
        });
        setError(
          err instanceof Error
            ? `${err.message} (showing owned agents only)`
            : "Dashboard partially unavailable"
        );
      } catch (fallbackErr) {
        setData(emptyDashboard());
        setError(
          fallbackErr instanceof Error
            ? fallbackErr.message
            : err instanceof Error
              ? err.message
              : "Failed to load dashboard"
        );
      }
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

      {connected && !isAuthenticated && !authBusy && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          Wallet connected - approve the sign-in prompt, or reconnect if it was dismissed.
        </div>
      )}

      {error && (
        <div className="border border-warn/40 bg-warn/10 px-4 py-3 font-mono text-xs text-warn">
          {error}
        </div>
      )}

      {isAuthenticated && loading && !data && (
        <div className="border border-grid bg-surface/40 px-4 py-3 font-mono text-xs text-muted-foreground">
          Loading dashboard…
        </div>
      )}

      {isAuthenticated && data && (
        <>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void reload()}
              disabled={loading}
              className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal hover:underline disabled:opacity-40"
            >
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          {data.creator_payout_wallet && (
            <div className="border border-grid bg-surface/40 px-4 py-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Creator earnings wallet
              </div>
              <p className="mt-2 break-all font-mono text-xs text-foreground">
                {data.creator_payout_wallet}
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Subscriptions send {Math.round((1 - (data.platform_fee_rate ?? 0.1)) * 100)}% here
                via Circle. You can claim this SOL later. The platform keeps{" "}
                {Math.round((data.platform_fee_rate ?? 0.1) * 100)}%.
              </p>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Listed for sale"
              value={String(data.counts.listed_for_sale)}
              accent="signal"
            />
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
            {data.listed_for_sale.length === 0 ? (
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
