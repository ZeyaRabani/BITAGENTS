"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { AgentCard } from "@/components/agents/AgentCard";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS, type AgentCategory } from "@/lib/agentsCatalog";

const CATEGORIES: AgentCategory[] = ["Monitor", "Research", "Alerts", "Automation", "Trading"];

function CreateAgentCard() {
  return (
    <Link href="/launch-agent" className="block h-full">
      <article
        className="group flex h-full flex-col bg-card p-5 transition hover:bg-signal/5"
        style={{
          borderWidth: 2,
          borderStyle: "dotted",
          borderColor: "color-mix(in srgb, var(--signal) 80%, transparent)",
        }}
      >
        <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-signal">
          New
        </div>
        <h3 className="mt-3 font-display text-lg font-bold text-foreground transition group-hover:text-signal">
          Create your agent
        </h3>
        <p className="mt-3 text-sm leading-snug text-muted-foreground">
          Describe a strategy in plain words. It compiles into an agent with its own wallet.
        </p>
        <div className="mt-auto pt-5">
          <span className="inline-flex w-full items-center justify-between bg-signal px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-primary-foreground transition group-hover:opacity-90">
            Start building
            <ArrowRight size={14} />
          </span>
        </div>
      </article>
    </Link>
  );
}

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
          <CreateAgentCard />
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
        {category && agents.length === 0 ? (
          <p className="mt-10 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            No {category} agents listed yet.
          </p>
        ) : null}
      </section>
    </AppShell>
  );
}
