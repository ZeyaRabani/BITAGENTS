import Link from "next/link";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import { agentAccentColor, AgentAvatar } from "@/components/launch/AgentAvatar";
import { LAUNCHED_AGENTS } from "@/lib/launchpadMock";

function agentScore(agent: (typeof LAUNCHED_AGENTS)[number]): number {
  const perDay = agent.runs / Math.max(1, agent.ageDays);
  return Math.round(800 + perDay * 40 + agent.runs / 20);
}

export function TrendingAgents() {
  const trending = [...LAUNCHED_AGENTS].sort((a, b) => b.volumeUsd - a.volumeUsd);

  return (
    <section id="trending">
      <div className="mx-auto max-w-7xl px-6 py-16 md:py-20">
        <div className="flex flex-col items-start justify-between gap-4 px-6 md:flex-row md:items-end">
          <h2 className="font-display text-4xl font-bold leading-tight md:text-5xl">
            Trending agents now
          </h2>
          <Link
            href="/launch"
            className="inline-flex shrink-0 items-center gap-2 rounded-full border border-grid px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] transition hover:border-signal hover:text-signal"
          >
            See Full Launchpad <ArrowUpRight size={14} />
          </Link>
        </div>

        <div className="scrollbar-none mt-10 flex gap-6 overflow-x-auto px-6 pb-4">
          {trending.map((agent) => {
            const color = agentAccentColor(agent.avatarSeed);
            const score = agentScore(agent);
            return (
              <Link
                key={agent.id}
                href={`/agents/${agent.id}`}
                className="group flex w-[320px] shrink-0 flex-col overflow-hidden rounded-3xl border border-grid bg-card transition hover:border-signal"
              >
                <div
                  className="flex aspect-square items-center justify-center"
                  style={{ background: `linear-gradient(135deg, ${color}40, ${color}10)` }}
                >
                  <AgentAvatar seed={agent.avatarSeed} size={72} />
                </div>
                <div className="flex flex-1 flex-col p-5">
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-lg font-bold">{agent.name}</h3>
                    <span className="rounded-full bg-surface-2 px-2.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
                      {agent.category}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                    {agent.description}
                  </p>
                  <div className="mt-5 flex items-end justify-between pt-4">
                    <div>
                      <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                        Live score
                      </div>
                      <div className="mt-1 font-display text-2xl font-bold tabular-nums" style={{ color }}>
                        {score.toLocaleString()}
                      </div>
                    </div>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-4 py-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-foreground transition group-hover:bg-signal group-hover:text-background">
                      Launch <ArrowRight size={12} />
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}
