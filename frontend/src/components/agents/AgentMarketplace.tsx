"use client";

import { useEffect, useRef, useState } from "react";
import { Filter, Search } from "lucide-react";
import { MarketplaceFeaturedAgents } from "@/components/agents/MarketplaceFeaturedAgents";
import { AppShell } from "@/components/AppShell";
import { FEATURED_AGENTS } from "@/lib/agentsCatalog";

const FILTERS = [
  { id: "all", label: "All agents" },
  { id: "verified", label: "Verified" },
  { id: "community", label: "Community" },
] as const;

export function AgentMarketplace() {
  const [listedCount, setListedCount] = useState(FEATURED_AGENTS.length);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (!filterRef.current?.contains(event.target as Node)) {
        setFilterOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const activeFilter = FILTERS.find((item) => item.id === filter) ?? FILTERS[0];

  return (
    <AppShell
      title="Agent Marketplace"
      subtitle="Discover and run BIT Agents. Launch your own from Launch Agents - public agents appear here."
    >
      <div className="mt-8 grid gap-6">
        <section>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Featured agents
            </h2>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {listedCount} listed
            </span>
          </div>

          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative w-full flex-1 sm:max-w-sm">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search agents…"
                className="w-full border border-grid bg-background py-2 pl-9 pr-3 font-mono text-sm text-foreground placeholder:text-muted-foreground"
              />
            </label>
            <div ref={filterRef} className="relative">
              <button
                type="button"
                onClick={() => setFilterOpen((open) => !open)}
                className={`inline-flex items-center gap-2 border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition ${
                  filter === "all"
                    ? "border-grid text-muted-foreground hover:border-signal/50"
                    : "border-signal bg-signal/10 text-signal"
                }`}
              >
                <Filter size={12} />
                Filter
                {filter !== "all" ? ` · ${activeFilter.label}` : ""}
              </button>
              {filterOpen && (
                <div className="absolute right-0 z-20 mt-2 min-w-44 border border-grid bg-background p-1 shadow-lg">
                  {FILTERS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        setFilter(item.id);
                        setFilterOpen(false);
                      }}
                      className={`block w-full px-3 py-2 text-left font-mono text-[10px] uppercase tracking-[0.14em] ${
                        filter === item.id
                          ? "bg-signal/10 text-signal"
                          : "text-muted-foreground hover:bg-surface/60 hover:text-foreground"
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <MarketplaceFeaturedAgents
            query={query}
            filter={filter}
            onCountChange={setListedCount}
          />
        </section>
      </div>
    </AppShell>
  );
}
