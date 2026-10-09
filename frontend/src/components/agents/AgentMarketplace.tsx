"use client";

import { useState } from "react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { AppShell } from "@/components/AppShell";
import { AGENT_CATEGORIES, FEATURED_AGENTS, type AgentCategory } from "@/lib/agentsCatalog";

const CATEGORY_FILTERS: { id: "all" | AgentCategory; label: string }[] = [
  { id: "all", label: "All" },
  ...AGENT_CATEGORIES.map((item) => ({ id: item.name, label: item.name })),
];

export function AgentMarketplace() {
  const [listedCount, setListedCount] = useState(FEATURED_AGENTS.length);
  const [category, setCategory] = useState<"all" | AgentCategory>("all");

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Pay per task on Solana - launch your own from the Launchpad."
    >
      <div className="mt-2 flex flex-wrap gap-2">
        {CATEGORY_FILTERS.map((item) => {
          const active = category === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setCategory(item.id)}
              className={`rounded-full border px-3.5 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] transition ${
                active
                  ? "border-signal bg-signal text-primary-foreground"
                  : "border-grid bg-surface/40 text-muted-foreground hover:border-signal/50 hover:text-foreground"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-between gap-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
          Verified agents
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {listedCount} listed
        </span>
      </div>

      <div className="mt-4">
        <MarketplaceFeaturedAgents category={category} onCountChange={setListedCount} />
      </div>
    </AppShell>
  );
}
