import Link from "next/link";
import { AgentAvatar } from "./AgentAvatar";
import { formatUsd, type LaunchedAgent } from "@/lib/launchpadMock";

const STATUS_STYLE: Record<LaunchedAgent["status"], string> = {
  LIVE: "border-signal text-signal",
  BONDING: "border-warn text-warn",
  TESTING: "border-grid text-muted-foreground",
};

export function AgentCard({ agent }: { agent: LaunchedAgent }) {
  return (
    <Link
      href={`/agents/${agent.id}`}
      className="group flex flex-col gap-3 border border-grid bg-surface/40 p-4 transition hover:border-signal hover:bg-surface"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <AgentAvatar seed={agent.avatarSeed} />
          <div>
            <div className="font-display text-sm font-bold leading-tight">{agent.name}</div>
            <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
              ${agent.ticker} · by {agent.creator}
            </div>
          </div>
        </div>
        <span
          className={`shrink-0 border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.14em] ${STATUS_STYLE[agent.status]}`}
        >
          {agent.status}
        </span>
      </div>

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{agent.description}</p>

      <div className="mt-auto grid grid-cols-3 gap-2 border-t border-grid pt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
        <div>
          <div className="text-muted-foreground/70">Age</div>
          <div className="mt-0.5 tabular-nums text-foreground">{agent.ageDays}d</div>
        </div>
        <div>
          <div className="text-muted-foreground/70">Runs</div>
          <div className="mt-0.5 tabular-nums text-foreground">{agent.runs.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-muted-foreground/70">Volume</div>
          <div className="mt-0.5 tabular-nums text-signal">{formatUsd(agent.volumeUsd)}</div>
        </div>
      </div>
    </Link>
  );
}
