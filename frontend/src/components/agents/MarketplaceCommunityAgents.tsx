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
 * the fixed AgentCategory enum Verified agents use, so the category filter
 * matches case-insensitively instead of requiring an exact enum match. */
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

  const filtered = useMemo(
    () =>
      agents.filter(
        (agent) => !category || agent.category?.toLowerCase() === category.toLowerCase()
      ),
    [agents, category]
  );

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
