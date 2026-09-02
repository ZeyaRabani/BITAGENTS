import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { AgentCard } from "@/components/launch/AgentCard";
import { LAUNCHED_AGENTS } from "@/lib/launchpadMock";

export function TrendingAgents() {
  const trending = [...LAUNCHED_AGENTS].sort((a, b) => b.volumeUsd - a.volumeUsd).slice(0, 6);

  return (
    <section id="trending" className="border-b border-grid">
      <div className="mx-auto max-w-7xl px-6 py-16 md:py-20">
        <div className="flex flex-col items-start justify-between gap-4 md:flex-row md:items-end">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Launchpad</div>
            <h2 className="mt-4 font-display text-4xl font-bold leading-tight md:text-5xl">
              Trending agents now
            </h2>
            <p className="mt-3 max-w-lg text-sm text-muted-foreground">
              Live agents, ranked by volume. Anyone can launch one — describe what it does, pick a model, ship it.
            </p>
          </div>
          <Link
            href="/launch"
            className="inline-flex shrink-0 items-center gap-2 border border-grid bg-surface/40 px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-[0.14em] transition hover:border-signal hover:text-signal"
          >
            See Full Launchpad <ArrowUpRight size={14} />
          </Link>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {trending.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      </div>
    </section>
  );
}
