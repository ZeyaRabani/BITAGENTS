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
  const showDcaStats = agent.slug === "dca" && !preview;
  const isVerified = Boolean(agent.verified ?? agent.source === "catalog");
  const href = agent.href ?? `/agents/${agent.slug}`;

  const inner = (
    <article className="group flex h-full flex-col border border-grid bg-surface/40 p-5 transition hover:border-signal/60 hover:bg-surface/70">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 items-center justify-center border border-grid bg-background/80 text-signal">
          <Icon size={18} strokeWidth={1.75} />
        </div>
        {isVerified ? (
          <span className="border border-signal/50 bg-signal/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal">
            Verified
          </span>
        ) : (
          <span className="border border-grid px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Community
          </span>
        )}
      </div>

      <h3 className="mt-4 font-display text-lg font-bold transition group-hover:text-signal">
        {agent.name}
      </h3>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {agent.category}
        {agent.pricePerTask ? ` · ${agent.pricePerTask}` : ""}
      </p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{agent.tagline}</p>

      {showDcaStats && (
        <div className="mt-5 grid grid-cols-2 gap-3 border-t border-grid pt-4 sm:grid-cols-3">
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
        {preview ? (
          <span className="inline-flex w-full items-center justify-between border border-grid bg-background/60 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Preview only
          </span>
        ) : agent.available ? (
          <span className="inline-flex w-full items-center justify-between border border-grid bg-background/60 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
            {agent.source === "launched" ? "View agent" : "Configure agent"}
            <ArrowRight size={14} />
          </span>
        ) : (
          <span className="inline-flex w-full items-center justify-between border border-grid/70 bg-background/30 px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Coming soon
          </span>
        )}
      </div>
    </article>
  );

  if (preview || !agent.available) {
    return <div className={`h-full ${preview ? "" : "opacity-80"}`}>{inner}</div>;
  }

  return (
    <Link href={href} className="block h-full">
      {inner}
    </Link>
  );
}
