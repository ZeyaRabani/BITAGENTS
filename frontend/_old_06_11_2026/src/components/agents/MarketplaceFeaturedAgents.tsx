"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentCard } from "@/components/agents/AgentCard";
import { FEATURED_AGENTS, type AgentCategory } from "@/lib/agentsCatalog";
import {
  fetchPlatformMetrics,
  formatMetricNumber,
  formatVolumeSol,
} from "@/lib/dcaPlanClient";

/** The hand-coded, official agents -- shown under "Verified" in the
 * marketplace, mirroring the Verified/Community split from Harshal's
 * hr-marketplace branch (agreed on in the Sept 28 meeting as the direction
 * to combine both builds' UI). */
export function MarketplaceFeaturedAgents({
  category,
}: {
  category?: AgentCategory | null;
}) {
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
      FEATURED_AGENTS.filter((agent) => !category || agent.category === category).map(
        (agent) => {
          if (agent.slug !== "dca") return agent;
          return {
            ...agent,
            runs: totalRuns ?? agent.runs,
            volumeSol: volumeSol ?? agent.volumeSol,
          };
        }
      ),
    [category, totalRuns, volumeSol]
  );

  if (agents.length === 0) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <AgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
