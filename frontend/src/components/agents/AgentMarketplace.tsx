"use client";

import { useMemo, useState } from "react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { MarketplaceCommunityAgents } from "@/components/agents/MarketplaceCommunityAgents";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS, type AgentCategory } from "@/lib/agentsCatalog";

const CATEGORIES: AgentCategory[] = ["Monitor", "Research", "Alerts", "Automation", "Trading"];

export function AgentMarketplace() {
  const [category, setCategory] = useState<AgentCategory | null>(null);
  const [communityCount, setCommunityCount] = useState<number | null>(null);

  const listedCount = useMemo(
    () => FEATURED_AGENTS.filter((agent) => !category || agent.category === category).length,
    [category]
  );

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Pay per task on Solana - launch your own from the Launchpad."
    >
      <div className="mt-6 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setCategory(null)}
          className={`border-2 px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${
            category === null
              ? "border-signal bg-signal/10 text-signal"
              : "border-grid text-muted-foreground hover:border-signal/40 hover:text-foreground"
          }`}
        >
          All
        </button>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategory(cat)}
            className={`border-2 px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${
              category === cat
                ? "border-signal bg-signal/10 text-signal"
                : "border-grid text-muted-foreground hover:border-signal/40 hover:text-foreground"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {category && listedCount === 0 && communityCount === 0 && (
        <p className="mt-10 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          No {category} agents listed yet.
        </p>
      )}

      <div className="mt-8 grid gap-10">
        <section>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Verified agents
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {listedCount} listed
            </span>
          </div>

          <MarketplaceFeaturedAgents category={category} />
        </section>

        {communityCount !== 0 && (
          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
                Community agents
              </h2>
              {communityCount !== null && (
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  {communityCount} listed
                </span>
              )}
            </div>

            <MarketplaceCommunityAgents category={category} onCount={setCommunityCount} />
          </section>
        )}
      </div>
    </AppShell>
  );
}
