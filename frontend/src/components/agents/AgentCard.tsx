"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { MarketplaceAgent } from "@/lib/agentsCatalog";

function agentInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function AgentCard({
  agent,
  preview = false,
}: {
  agent: MarketplaceAgent;
  preview?: boolean;
}) {
  const showDcaStats = agent.slug === "dca" && !preview;
  const href = agent.href ?? `/agents/${agent.slug}`;

  const inner = (
    <article className="group flex h-full flex-col rounded-2xl border border-grid bg-surface/50 p-5 transition hover:border-signal hover:bg-surface/80">
      <div className="flex items-start justify-between gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-grid bg-background/80 font-mono text-xs font-bold uppercase tracking-[0.08em] text-signal">
          {agentInitials(agent.name)}
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {agent.category}
        </span>
      </div>

      <h3 className="mt-4 font-display text-lg font-bold transition group-hover:text-signal">
        {agent.name}
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{agent.tagline}</p>

      {showDcaStats && (
        <div className="mt-4 grid grid-cols-3 gap-2 border-t border-grid pt-3">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              Per task
            </div>
            <div className="mt-1 font-mono text-[11px] font-semibold tabular-nums text-signal">
              {agent.pricePerTask ?? "-"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              Total tx
            </div>
            <div className="mt-1 font-mono text-[11px] font-semibold tabular-nums">
              {agent.runs ?? "-"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              Volume
            </div>
            <div className="mt-1 font-mono text-[11px] font-semibold tabular-nums text-signal">
              {agent.volumeSol ?? "-"}
            </div>
          </div>
        </div>
      )}

      <div className="mt-auto flex items-center justify-between gap-3 pt-5">
        <span className="font-display text-lg font-bold tabular-nums text-signal">
          {agent.rating > 0 ? agent.rating.toFixed(1) : "—"}
        </span>
        {preview ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-grid px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Preview
          </span>
        ) : agent.available ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-grid px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
            {agent.source === "launched" ? "View" : "Configure"}
            <ArrowRight size={12} />
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-grid/70 px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Soon
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
