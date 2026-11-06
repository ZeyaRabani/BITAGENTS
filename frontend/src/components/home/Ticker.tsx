const TICKER_AGENTS = [{ sym: "DCA", runs: 0, volumeUsd: 0 }];

function formatUsd(value: number): string {
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

export function Ticker() {
  const items = TICKER_AGENTS.map((agent) => ({
    sym: agent.sym,
    px: `${agent.runs.toLocaleString()} runs`,
    ch: formatUsd(agent.volumeUsd),
  }));
  const row = [...items, ...items];
  return (
    <div className="border-y-2 border-grid bg-surface/40">
      <div className="ticker-mask overflow-hidden">
        <div className="flex w-max animate-ticker gap-10 px-6 py-3 font-mono text-xs">
          {row.map((it, i) => (
            <span key={i} className="flex items-center gap-3 whitespace-nowrap">
              <span className="text-signal">@{it.sym}</span>
              <span className="text-muted-foreground tabular-nums">{it.px}</span>
              <span className="tabular-nums text-foreground">{it.ch}</span>
              <span className="text-muted-foreground/50">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
