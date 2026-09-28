"use client";

import { useState } from "react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { MarketplaceCommunityAgents } from "@/components/agents/MarketplaceCommunityAgents";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS } from "@/lib/agentsCatalog";

export function AgentMarketplace() {
  const listedCount = FEATURED_AGENTS.length;
  const [communityCount, setCommunityCount] = useState<number | null>(null);

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Pay per task on Solana - launch your own from the Launchpad."
    >
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

          <MarketplaceFeaturedAgents />
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

            <MarketplaceCommunityAgents onCount={setCommunityCount} />
          </section>
        )}
      </div>
    </AppShell>
  );
}
