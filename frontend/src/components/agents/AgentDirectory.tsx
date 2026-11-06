"use client";

import { useMemo, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS, type AgentCategory } from "@/lib/agentsCatalog";

const CATEGORIES: AgentCategory[] = ["Monitor", "Research", "Alerts", "Automation", "Trading"];

export function AgentDirectory() {
  const [category, setCategory] = useState<AgentCategory | null>(null);

  const agents = useMemo(
    () => FEATURED_AGENTS.filter((agent) => !category || agent.category === category),
    [category]
  );

  return (
    <AppShell title="Agent Marketplace">
      <div className="relative flex flex-wrap gap-2">
        <div className="fixed top-1/4 z-[-1] hidden h-96 w-1/2 rounded-full bg-primary/10 blur-3xl md:block" />
        <button
          type="button"
          onClick={() => setCategory(null)}
          className={`rounded-full px-4 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${
            category === null
              ? "bg-signal text-background"
              : "border border-grid text-muted-foreground hover:border-signal hover:text-foreground"
          }`}
        >
          All
        </button>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategory(cat)}
            className={`rounded-full px-4 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${
              category === cat
                ? "bg-signal text-background"
                : "border border-grid text-muted-foreground hover:border-signal hover:text-foreground"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {agents.length === 0 ? (
        <p className="mt-10 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          No {category ? `${category} ` : ""}agents listed yet.
        </p>
      ) : (
        <section className="mt-8">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Verified agents
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {agents.length} listed
            </span>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </section>
      )}
    </AppShell>
  );
}
