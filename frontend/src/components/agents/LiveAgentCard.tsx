"use client";

import { ArrowRight, Bell } from "lucide-react";
import Link from "next/link";
import type { LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";

/** Same visual shape as AgentCard for launched community agents. */
export function LiveAgentCard({ agent }: { agent: LaunchedAgentRecord }) {
  return (
    <Link href={`/agents/custom/${agent.id}`} className="block h-full">
      <article className="group flex h-full flex-col border border-grid bg-card p-5 transition hover:border-signal">
        <div className="flex items-start justify-between gap-3">
          <div className="flex h-10 w-10 items-center justify-center border border-grid text-signal">
            <Bell size={18} strokeWidth={1.75} />
          </div>
          {agent.status === "testing" && (
            <span className="border border-warn/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-warn">
              Testing
            </span>
          )}
        </div>

        <h3 className="mt-4 font-display text-lg font-bold transition group-hover:text-signal">
          {agent.name ?? "Untitled agent"}
        </h3>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {agent.category ?? "Uncategorized"}
        </p>
        {agent.description && (
          <p className="mt-3 line-clamp-2 text-sm leading-snug text-muted-foreground">
            {agent.description}
          </p>
        )}

        <div className="mt-5 grid grid-cols-3 gap-3 border-t border-grid pt-4">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              Per task
            </div>
            <div className="mt-1 font-display text-sm font-bold tabular-nums text-signal">-</div>
          </div>
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              Total tx
            </div>
            <div className="mt-1 font-display text-sm font-bold tabular-nums">
              {agent.runs > 0 ? agent.runs.toLocaleString() : "-"}
            </div>
          </div>
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
              Volume
            </div>
            <div className="mt-1 font-display text-sm font-bold tabular-nums">
              {agent.volume_usd > 0 ? `$${agent.volume_usd.toLocaleString()}` : "-"}
            </div>
          </div>
        </div>

        <div className="mt-auto pt-5">
          <span className="inline-flex w-full items-center justify-between border border-grid px-4 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
            Configure agent
            <ArrowRight size={14} />
          </span>
        </div>
      </article>
    </Link>
  );
}
