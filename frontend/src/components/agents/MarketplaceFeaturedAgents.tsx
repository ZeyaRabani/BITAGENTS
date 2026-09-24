"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { LiveAgentCard } from "@/components/agents/LiveAgentCard";
import { FEATURED_AGENTS } from "@/lib/agentsCatalog";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import {
  fetchPlatformMetrics,
  formatMetricNumber,
  formatVolumeSol,
} from "@/lib/dcaPlanClient";
import { fetchVisibleCustomAgents, type LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";

export function MarketplaceFeaturedAgents() {
  const { token } = useDcaWalletAuth();
  const [totalRuns, setTotalRuns] = useState<string | null>(null);
  const [volumeSol, setVolumeSol] = useState<string | null>(null);
  const [customAgents, setCustomAgents] = useState<LaunchedAgentRecord[]>([]);

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
    void fetchVisibleCustomAgents(token ?? undefined).then(setCustomAgents);
  }, [token]);

  const agents = useMemo(
    () =>
      FEATURED_AGENTS.map((agent) => {
        if (agent.slug !== "dca") return agent;
        return {
          ...agent,
          runs: totalRuns ?? agent.runs,
          volumeSol: volumeSol ?? agent.volumeSol,
        };
      }),
    [totalRuns, volumeSol]
  );

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
      {customAgents.map((agent) => (
        <LiveAgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
