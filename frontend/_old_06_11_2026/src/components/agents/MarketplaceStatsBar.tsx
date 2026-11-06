"use client";

import { useEffect, useState } from "react";
import { Stat } from "@/components/AppShell";
import { fetchPlatformMetrics, formatMetricNumber } from "@/lib/dcaPlanClient";
import { MARKETPLACE_STATS } from "@/lib/agentsCatalog";

export function MarketplaceStatsBar() {
  const [stats, setStats] = useState({
    liveAgents: MARKETPLACE_STATS.liveAgents,
    tasks24h: MARKETPLACE_STATS.tasks24h,
    activeBuilders: MARKETPLACE_STATS.activeBuilders,
    uptime30d: MARKETPLACE_STATS.uptime30d,
  });

  useEffect(() => {
    void fetchPlatformMetrics().then((metrics) => {
      if (!metrics) return;
      setStats({
        liveAgents: String(Math.max(1, metrics.active_plans || 1)),
        tasks24h: formatMetricNumber(metrics.executions_24h ?? 0),
        activeBuilders: formatMetricNumber(metrics.total_users ?? 0),
        uptime30d: metrics.total_executions > 0 ? "99.2%" : MARKETPLACE_STATS.uptime30d,
      });
    });
  }, []);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Stat label="Active DCA plans" value={stats.liveAgents} accent="signal" />
      <Stat label="DCA swaps · 24h" value={stats.tasks24h} />
      <Stat label="DCA users" value={stats.activeBuilders} />
      {/* <Stat label="Uptime · 30d" value={stats.uptime30d} accent="signal" /> */}
    </div>
  );
}
