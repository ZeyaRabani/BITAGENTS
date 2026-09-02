import { LAUNCHED_AGENTS, formatUsd } from "@/lib/launchpadMock";

export function PlatformMetrics() {
  const totalVolume = LAUNCHED_AGENTS.reduce((s, a) => s + a.volumeUsd, 0);
  const totalRuns = LAUNCHED_AGENTS.reduce((s, a) => s + a.runs, 0);
  const totalFees = LAUNCHED_AGENTS.reduce((s, a) => s + a.feesUsd, 0);
  const liveCount = LAUNCHED_AGENTS.filter((a) => a.status === "LIVE").length;

  const stats: [string, string][] = [
    [formatUsd(totalVolume), "Total Volume"],
    [totalRuns.toLocaleString(), "Agent Runs"],
    [formatUsd(totalFees), "Fees Earned"],
    [`${liveCount}`, "Agents Live"],
  ];

  return (
    <section className="border-b border-grid bg-surface/30">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-px bg-border md:grid-cols-4">
        {stats.map(([value, label]) => (
          <div key={label} className="bg-background px-6 py-6">
            <div className="font-display text-2xl font-bold tabular-nums md:text-3xl">{value}</div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {label}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
