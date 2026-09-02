"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Search } from "lucide-react";
import { LaunchTicker } from "@/components/launch/LaunchTicker";
import { AgentCard } from "@/components/launch/AgentCard";
import { LAUNCHED_AGENTS, type LaunchedAgent } from "@/lib/launchpadMock";

type SortKey = "newest" | "volume" | "runs";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "volume", label: "Volume" },
  { key: "runs", label: "Most Run" },
];

const CATEGORIES: ("All" | LaunchedAgent["category"])[] = ["All", "Trading", "Research", "Monitoring", "Utility"];

export default function LaunchPage() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("All");

  const agents = useMemo(() => {
    let list = [...LAUNCHED_AGENTS];
    if (category !== "All") list = list.filter((a) => a.category === category);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      list = list.filter(
        (a) => a.name.toLowerCase().includes(q) || a.ticker.toLowerCase().includes(q) || a.creator.toLowerCase().includes(q)
      );
    }
    if (sort === "newest") list.sort((a, b) => a.ageDays - b.ageDays);
    if (sort === "volume") list.sort((a, b) => b.volumeUsd - a.volumeUsd);
    if (sort === "runs") list.sort((a, b) => b.runs - a.runs);
    return list;
  }, [query, sort, category]);

  return (
    <div className="min-h-screen">
      <section className="border-b border-grid">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 sm:py-14">
          <h1 className="font-display text-4xl font-bold leading-[1.02] tracking-tight md:text-5xl">
            Launch your <span className="text-signal">AI agent</span>.
            <br />
            Let the market run it.
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground">
            Describe what you want your agent to do, pick a model, and ship it. No code, no API keys —
            anyone can launch an agent and anyone can put it to work.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/launch/create"
              className="group inline-flex items-center gap-2 bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90"
            >
              Launch An Agent <ArrowUpRight size={16} className="transition group-hover:translate-x-0.5" />
            </Link>
            <a
              href="#feed"
              className="inline-flex items-center gap-2 border border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal"
            >
              Browse Agents
            </a>
          </div>
        </div>
      </section>

      <LaunchTicker />

      <section id="feed" className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-4 border-b border-grid pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 border border-grid bg-surface/40 px-3 py-2 sm:w-80">
            <Search size={14} className="shrink-0 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search agents by name, ticker, creator"
              className="w-full bg-transparent font-mono text-xs uppercase tracking-[0.08em] text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  onClick={() => setCategory(c)}
                  className={`border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] transition ${
                    category === c
                      ? "border-signal bg-surface/60 text-signal"
                      : "border-grid text-muted-foreground hover:border-signal/60 hover:text-foreground"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="ml-2 flex gap-1.5 border-l border-grid pl-2">
              {SORTS.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setSort(s.key)}
                  className={`border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] transition ${
                    sort === s.key
                      ? "border-signal bg-surface/60 text-signal"
                      : "border-grid text-muted-foreground hover:border-signal/60 hover:text-foreground"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {agents.length === 0 ? (
          <div className="py-16 text-center font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
            No agents match "{query}"
          </div>
        ) : (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
