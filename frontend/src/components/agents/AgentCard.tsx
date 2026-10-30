"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { AGENT_ICONS } from "@/lib/agentsCatalog";
import type { MarketplaceAgent } from "@/lib/agentsCatalog";

export function AgentCard({
  agent,
  preview = false,
}: {
  agent: MarketplaceAgent;
  preview?: boolean;
}) {
  const Icon = AGENT_ICONS[agent.iconId];

  const inner = (
    <article className="group flex h-full flex-col border border-grid bg-card p-5 transition hover:border-signal">
      {/* <div className="flex h-10 w-10 items-center justify-center border border-grid text-signal">
        <Icon size={18} strokeWidth={1.75} />
      </div> */}

      <h3 className="font-display text-lg font-bold transition group-hover:text-signal">
        {agent.name}
      </h3>
      {/* <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {agent.category}
      </p> */}
      {agent.tagline && (
        <p className="mt-3 text-sm leading-snug text-muted-foreground">{agent.tagline}</p>
      )}

      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-grid pt-4">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
            Per task
          </div>
          <div className="mt-1 font-display text-sm font-bold tabular-nums text-signal">
            {agent.pricePerTask ?? "-"}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
            Total tx
          </div>
          <div className="mt-1 font-display text-sm font-bold tabular-nums">
            {agent.runs ?? "-"}
          </div>
        </div>
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
            Volume
          </div>
          <div className="mt-1 font-display text-sm font-bold tabular-nums">
            {agent.volumeSol ?? "-"}
          </div>
        </div>
      </div>

      <div className="mt-auto pt-5">
        {agent.available ? (
          <span className="inline-flex w-full items-center justify-between border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
            Configure agent
            <ArrowRight size={14} />
          </span>
        ) : (
          <span className="inline-flex w-full items-center justify-between border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Coming soon
          </span>
        )}
      </div>
    </article>
  );

  if (preview || !agent.available) {
    return <div className={`h-full ${agent.available ? "" : "opacity-80"}`}>{inner}</div>;
  }

  return (
    <Link href={`/agents/${agent.slug}`} className="block h-full">
      {inner}
    </Link>
  );
}
