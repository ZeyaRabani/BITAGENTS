"use client";

import { useEffect, useMemo, useState } from "react";
import { LiveAgentCard } from "@/components/agents/LiveAgentCard";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import type { AgentCategory } from "@/lib/agentsCatalog";
import { fetchVisibleCustomAgents, type LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";

/** User-launched agents -- shown under "Community", separate from the
 * hand-coded Verified section, so visitors can tell official agents from
 * ones anyone launched. Exposes its own count via onCount so the parent
 * section header can show "N listed" without a second fetch.
 *
 * Launched agents store a free-text category (set by the builder LLM), not
 * the fixed AgentCategory enum Verified agents use -- in practice the LLM
 * writes variants like "Monitoring" for the enum value "Monitor", so the
 * filter checks either string contains the other (case-insensitive)
 * instead of requiring an exact match, which would silently hide agents
 * with a plausible but non-identical category label. */
export function MarketplaceCommunityAgents({
  category,
  onCount,
}: {
  category?: AgentCategory | null;
  onCount?: (n: number) => void;
}) {
  const { token } = useDcaWalletAuth();
  const [agents, setAgents] = useState<LaunchedAgentRecord[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    void fetchVisibleCustomAgents(token ?? undefined).then((list) => {
      setAgents(list);
      setLoaded(true);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const filtered = useMemo(() => {
    if (!category) return agents;
    const target = category.toLowerCase();
    return agents.filter((agent) => {
      const agentCategory = agent.category?.toLowerCase();
      return !!agentCategory && (agentCategory.includes(target) || target.includes(agentCategory));
    });
  }, [agents, category]);

  useEffect(() => {
    if (loaded) onCount?.(filtered.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, filtered]);

  if (loaded && filtered.length === 0) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {filtered.map((agent) => (
        <LiveAgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
