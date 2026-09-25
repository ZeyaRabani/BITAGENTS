"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { FEATURED_AGENTS, type MarketplaceAgent } from "@/lib/agentsCatalog";
import {
  fetchPlatformMetrics,
  formatMetricNumber,
  formatVolumeSol,
} from "@/lib/dcaPlanClient";
import { fetchPublicLaunchedAgents } from "@/lib/launchAgentClient";
import { mapLaunchedToMarketplaceAgent } from "@/lib/launchMarketplace";

export function MarketplaceFeaturedAgents({
  query = "",
  filter = "all",
  onCountChange,
}: {
  query?: string;
  filter?: "all" | "verified" | "community";
  onCountChange?: (count: number) => void;
}) {
  const [totalRuns, setTotalRuns] = useState<string | null>(null);
  const [volumeSol, setVolumeSol] = useState<string | null>(null);
  const [launched, setLaunched] = useState<MarketplaceAgent[]>([]);

  useEffect(() => {
    void fetchPlatformMetrics().then((metrics) => {
      if (!metrics) return;
      setTotalRuns(
        formatMetricNumber(metrics.successful_swaps ?? metrics.total_executions ?? 0)
      );
      setVolumeSol(formatVolumeSol(metrics.total_volume_sol ?? 0));
    });
  }, []);

  useEffect(() => {
    void fetchPublicLaunchedAgents().then((agents) => {
      setLaunched(agents.map(mapLaunchedToMarketplaceAgent));
    });
  }, []);

  const agents = useMemo(() => {
    const catalog = FEATURED_AGENTS.map((agent) => {
      const base: MarketplaceAgent = {
        ...agent,
        verified: true,
        source: "catalog",
      };
      if (agent.slug !== "dca") return base;
      return {
        ...base,
        runs: totalRuns ?? agent.runs,
        volumeSol: volumeSol ?? agent.volumeSol,
      };
    });
    const merged = [...catalog, ...launched];
    const q = query.trim().toLowerCase();
    return merged.filter((agent) => {
      if (filter === "verified" && !agent.verified) return false;
      if (filter === "community" && agent.verified) return false;
      if (!q) return true;
      return (
        agent.name.toLowerCase().includes(q) ||
        agent.tagline.toLowerCase().includes(q) ||
        agent.description.toLowerCase().includes(q) ||
        agent.category.toLowerCase().includes(q)
      );
    });
  }, [totalRuns, volumeSol, launched, query, filter]);

  useEffect(() => {
    onCountChange?.(agents.length);
  }, [agents.length, onCountChange]);

  if (agents.length === 0) {
    return (
      <div className="border border-grid bg-surface/40 px-4 py-8 text-center font-mono text-xs text-muted-foreground">
        No agents match this search or filter.
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
