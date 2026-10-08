"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { AGENT_ICONS } from "@/lib/agentsCatalog";
import type { MarketplaceAgent } from "@/lib/agentsCatalog";
import { agentAccentColor } from "@/components/launch/AgentAvatar";

export function AgentCard({ agent }: { agent: MarketplaceAgent }) {
  const Icon = AGENT_ICONS[agent.iconId];
  const showDcaStats = agent.slug === "dca";
  const accent = agentAccentColor(agent.id);

  const inner = (
    <article className="group flex h-full flex-col overflow-hidden rounded-3xl border border-grid bg-card transition hover:border-signal">
      <div
        className="flex aspect-[4/3] items-center justify-center"
        style={{ background: `linear-gradient(135deg, ${accent}33, ${accent}0d)` }}
      >
        <Icon size={40} strokeWidth={1.5} color={accent} />
      </div>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-bold transition group-hover:text-signal">
            {agent.name}
          </h3>
          <span className="rounded-full bg-surface-2 px-2.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
            {agent.category}
          </span>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{agent.tagline}</p>

        {showDcaStats && (
          <div className="mt-4 grid grid-cols-3 gap-3 border-t border-grid pt-4">
            <div>
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Per task</div>
              <div className="mt-1 font-display text-sm font-bold tabular-nums text-signal">{agent.pricePerTask ?? "-"}</div>
            </div>
            <div>
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Total tx</div>
              <div className="mt-1 font-display text-sm font-bold tabular-nums">{agent.runs ?? "-"}</div>
            </div>
            <div>
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Volume</div>
              <div className="mt-1 font-display text-sm font-bold tabular-nums text-signal">{agent.volumeSol ?? "-"}</div>
            </div>
          </div>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-grid pt-4">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Rating</div>
            <div className="mt-0.5 font-display text-base font-bold tabular-nums text-signal">{agent.rating.toFixed(1)}</div>
          </div>
          {agent.available ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-foreground transition group-hover:bg-signal group-hover:text-background">
              Configure <ArrowRight size={12} />
            </span>
          ) : (
            <span className="rounded-full bg-surface-2/60 px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Soon
            </span>
          )}
        </div>
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
