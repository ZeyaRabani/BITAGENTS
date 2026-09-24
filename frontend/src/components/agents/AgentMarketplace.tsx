import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { MarketplaceStatsBar } from "@/components/agents/MarketplaceStatsBar";
import { AppShell } from "@/components/AppShell";
import { AGENT_CATEGORIES, FEATURED_AGENTS } from "@/lib/agentsCatalog";

export function AgentMarketplace() {
  const listedCount = FEATURED_AGENTS.length;

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Pay per task on Solana - launch your own from the Launchpad."
    >
      {/* <MarketplaceStatsBar /> */}

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

          <MarketplaceFeaturedAgents />
        </section>
      </div>
    </AppShell>
  );
}
