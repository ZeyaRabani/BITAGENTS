"use client";

import Link from "next/link";

const trendingAgents = [
  {
    id: "volume",
    initials: "VO",
    name: "Volume Agent",
    category: "Trading",
    body: "Run volume campaigns on tokens that already trade. Deposit SOL and schedule buy/sell cycles through Jupiter.",
    href: "/agents/volume",
  },
  {
    id: "dca",
    initials: "DC",
    name: "DCA Agent",
    category: "Trading",
    body: "Set up recurring Solana buys from natural language. Schedule swaps and manage plans without leaving chat.",
    href: "/agents/dca",
  },
  {
    id: "hedge-fund",
    initials: "HE",
    name: "Hedge Fund Agent",
    category: "Trading",
    body: "Deposit SOL, run live Jupiter strategy sleeves, and liquidate back to SOL with risk-managed fees.",
    href: "/agents/hedge-fund",
  },
  {
    id: "kickstart-copilot",
    initials: "EA",
    name: "EasyA Analysis Agent",
    category: "Research",
    body: "Solana token analysis - live price, liquidity, holders, health scores, risk checks, and comparisons.",
    href: "/agents/kickstart-copilot",
  },
] as const;

export function Product() {
  return (
    <section id="product" className="border-b border-grid/70">
      <div className="mx-auto max-w-7xl px-6 py-16 md:py-20">
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
          <h2 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
            Trending agents now
          </h2>
          <Link
            href="/agents"
            className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground transition hover:text-signal"
          >
            See full launchpad →
          </Link>
        </div>

        <div className="mt-10 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {trendingAgents.map((agent) => (
            <Link
              key={agent.id}
              href={agent.href}
              className="group flex h-full flex-col rounded-2xl border border-grid bg-surface/50 p-5 transition hover:border-signal hover:bg-surface/80"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-grid bg-background/80 font-mono text-xs font-bold uppercase tracking-[0.08em] text-signal">
                  {agent.initials}
                </div>
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  {agent.category}
                </span>
              </div>
              <h3 className="mt-4 font-display text-base font-bold transition group-hover:text-signal">
                {agent.name}
              </h3>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                {agent.body}
              </p>
              <div className="mt-5 flex items-center justify-between border-t border-grid pt-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Live
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-grid px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-foreground transition group-hover:border-signal group-hover:text-signal">
                  Launch →
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
