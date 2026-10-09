const items = [
  { agent: "Volume Agent", action: "ran a Jupiter volume cycle", meta: "0.12 SOL · 2m ago" },
  { agent: "DCA Agent", action: "bought SOL → USDC on schedule", meta: "0.05 SOL · 5m ago" },
  { agent: "Hedge Fund Agent", action: "rebalanced a live sleeve", meta: "1.4 SOL · 8m ago" },
  { agent: "Yield Agent", action: "compared Kamino vs Save APYs", meta: "4.3% best · 11m ago" },
  { agent: "EasyA Analysis Agent", action: "scored a Solana mint", meta: "health 82 · 14m ago" },
  { agent: "Whale Tracking Agent", action: "flagged a watched wallet move", meta: "42 SOL · 18m ago" },
  { agent: "DCA Agent", action: "previewed a Jupiter quote", meta: "dry run · 22m ago" },
  { agent: "Volume Agent", action: "finished a Standard campaign leg", meta: "0.08 SOL · 27m ago" },
];

export function Ticker() {
  const row = [...items, ...items];
  return (
    <div className="border-y border-grid/80 bg-surface/30 backdrop-blur-sm">
      <div className="ticker-mask overflow-hidden">
        <div className="flex w-max animate-ticker gap-10 px-6 py-3.5 font-mono text-xs">
          {row.map((it, i) => (
            <span key={`${it.agent}-${i}`} className="flex items-center gap-3 whitespace-nowrap">
              <span className="text-signal">{it.agent}</span>
              <span className="text-muted-foreground">{it.action}</span>
              <span className="tabular-nums text-foreground/80">{it.meta}</span>
              <span className="text-muted-foreground/40">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
