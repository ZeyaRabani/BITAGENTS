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
  onCountChange,
}: {
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
    return [...catalog, ...launched];
  }, [totalRuns, volumeSol, launched]);

  useEffect(() => {
    onCountChange?.(agents.length);
  }, [agents.length, onCountChange]);

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
