import Link from "next/link";
import { AgentAvatar } from "./AgentAvatar";
import type { LaunchedAgent } from "@/lib/launchpadMock";

export function AgentCard({ agent }: { agent: LaunchedAgent }) {
  return (
    <Link
      href={`/agents/${agent.id}`}
      className="group flex flex-col gap-3 border-2 border-grid bg-surface/40 p-4 transition hover:border-signal hover:bg-surface"
    >
      <div className="flex items-center gap-3">
        <AgentAvatar seed={agent.avatarSeed} />
        <div>
          <div className="font-display text-sm font-bold leading-tight">{agent.name}</div>
          <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-muted-foreground">
            @{agent.handle} · by {agent.creator}
          </div>
        </div>
      </div>
    </Link>
  );
}
