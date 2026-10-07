"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { AGENT_ICONS } from "@/lib/agentsCatalog";
import type { MarketplaceAgent } from "@/lib/agentsCatalog";

export function AgentCard({ agent }: { agent: MarketplaceAgent }) {
  const Icon = AGENT_ICONS[agent.iconId];
  const showDcaStats = agent.slug === "dca";

  const inner = (
    <article className="group flex h-full flex-col bg-card p-5 transition hover:bg-surface-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 items-center justify-center text-signal">
          <Icon size={18} strokeWidth={1.75} />
        </div>
      </div>

      <h3 className="mt-4 font-display text-lg font-bold transition group-hover:text-signal">
        {agent.name}
      </h3>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {agent.category}
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{agent.tagline}</p>

      {showDcaStats && (
        <div className="mt-5 grid grid-cols-2 gap-3 pt-4 sm:grid-cols-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Per task
            </div>
            <div className="mt-1 font-display text-base font-bold tabular-nums text-signal md:text-lg">
              {agent.pricePerTask ?? "-"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Total tx
            </div>
            <div className="mt-1 font-display text-base font-bold tabular-nums md:text-lg">
              {agent.runs ?? "-"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Volume
            </div>
            <div className="mt-1 font-display text-base font-bold tabular-nums text-signal md:text-lg">
              {agent.volumeSol ?? "-"}
            </div>
          </div>
        </div>
      )}

      <div className="mt-auto pt-5">
        {agent.available ? (
          <span className="inline-flex w-full items-center justify-between bg-surface-2 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:bg-signal group-hover:text-background">
            Configure agent
            <ArrowRight size={14} />
          </span>
        ) : (
          <span className="inline-flex w-full items-center justify-between bg-surface-2/60 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Coming soon
          </span>
        )}
      </div>
    </article>
  );

  if (agent.available) {
    return (
      <Link href={`/agents/${agent.slug}`} className="block h-full">
        {inner}
      </Link>
    );
  }

  return <div className="h-full opacity-80">{inner}</div>;
}
