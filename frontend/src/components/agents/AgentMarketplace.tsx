"use client";

import { useState } from "react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS } from "@/lib/agentsCatalog";

export function AgentMarketplace() {
  const [listedCount, setListedCount] = useState(FEATURED_AGENTS.length);

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Launch your own from Launch Agents - public agents appear here."
    >
      <div className="mt-8 grid gap-6">
        <section>
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Featured agents
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {listedCount} listed
            </span>
          </div>

          <MarketplaceFeaturedAgents onCountChange={setListedCount} />
        </section>
      </div>
    </AppShell>
  );
}
