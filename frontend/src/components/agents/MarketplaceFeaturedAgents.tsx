"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { FEATURED_AGENTS } from "@/lib/agentsCatalog";
import {
  fetchPlatformMetrics,
  formatMetricNumber,
  formatVolumeSol,
} from "@/lib/dcaPlanClient";

/** The hand-coded, official agents -- shown under "Verified" in the
 * marketplace, mirroring the Verified/Community split from Harshal's
 * hr-marketplace branch (agreed on in the Sept 28 meeting as the direction
 * to combine both builds' UI). */
export function MarketplaceFeaturedAgents() {
  const [totalRuns, setTotalRuns] = useState<string | null>(null);
  const [volumeSol, setVolumeSol] = useState<string | null>(null);

  useEffect(() => {
    void fetchPlatformMetrics().then((metrics) => {
      if (!metrics) return;
      setTotalRuns(
        formatMetricNumber(metrics.successful_swaps ?? metrics.total_executions ?? 0)
      );
      setVolumeSol(formatVolumeSol(metrics.total_volume_sol ?? 0));
    });
  }, []);

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
    </div>
  );
}
