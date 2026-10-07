import Link from "next/link";
import { AgentAvatar, agentAccentColor } from "./AgentAvatar";
import { Sparkline } from "./Sparkline";
import type { LaunchedAgent } from "@/lib/launchpadMock";

/** A real, derived number (not decoration) -- runs scaled against age, so
 * an agent that's been live longer needs more usage to earn the same
 * score as a newer one. SwarmDojo's "rating per fighter" pattern, but
 * built from stats we actually have instead of an invented ELO. */
function agentScore(agent: LaunchedAgent): number {
  const perDay = agent.runs / Math.max(1, agent.ageDays);
  return Math.round(800 + perDay * 40 + agent.runs / 20);
}

export function AgentCard({ agent }: { agent: LaunchedAgent }) {
  const color = agentAccentColor(agent.avatarSeed);
  return (
    <Link
      href={`/agents/${agent.id}`}
      className="group flex flex-col gap-4 bg-card p-6 transition hover:bg-surface-2"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <AgentAvatar seed={agent.avatarSeed} />
          <div>
            <div className="font-display text-sm font-bold leading-tight">{agent.name}</div>
            <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
              @{agent.handle} · by {agent.creator}
            </div>
          </div>
        </div>
        <div className="shrink-0 bg-surface-2 px-2 py-1 text-right font-mono">
          <div className="text-sm font-bold tabular-nums" style={{ color }}>
            {agentScore(agent).toLocaleString()}
          </div>
          <div className="text-[8px] uppercase tracking-[0.1em] text-muted-foreground">rating</div>
        </div>
      </div>
      <Sparkline seed={agent.avatarSeed} color={color} />
    </Link>
  );
}
