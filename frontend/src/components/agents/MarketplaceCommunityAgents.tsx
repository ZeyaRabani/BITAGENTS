"use client";

import { useEffect, useState } from "react";
import { LiveAgentCard } from "@/components/agents/LiveAgentCard";
import { useDcaWalletAuth } from "@/hooks/useDcaWalletAuth";
import { fetchVisibleCustomAgents, type LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";

/** User-launched agents -- shown under "Community", separate from the
 * hand-coded Verified section, so visitors can tell official agents from
 * ones anyone launched. Exposes its own count via onCount so the parent
 * section header can show "N listed" without a second fetch. */
export function MarketplaceCommunityAgents({ onCount }: { onCount?: (n: number) => void }) {
  const { token } = useDcaWalletAuth();
  const [agents, setAgents] = useState<LaunchedAgentRecord[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    void fetchVisibleCustomAgents(token ?? undefined).then((list) => {
      setAgents(list);
      setLoaded(true);
      onCount?.(list.length);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (loaded && agents.length === 0) return null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {agents.map((agent) => (
        <LiveAgentCard key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
