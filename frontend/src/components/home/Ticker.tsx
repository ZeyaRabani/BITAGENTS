export function Ticker() {
  const items = [
    { sym: "wallet-watch", px: "142 runs", ch: "+2.4%" },
    { sym: "research-7", px: "89 reports", ch: "+1.1%" },
    { sym: "alert-bot", px: "56 alerts", ch: "+4.2%" },
    { sym: "auto-rebal", px: "31 jobs", ch: "+0.8%" },
    { sym: "meme-scout", px: "24 scans", ch: "+3.1%" },
    { sym: "arb-finder", px: "18 hits", ch: "+1.9%" },
    { sym: "AGENT·IDX", px: "48 live", ch: "+6.0%" },
    { sym: "TASK·VOL", px: "12.4k", ch: "+2.7%" },
  ];
  const row = [...items, ...items];
  return (
    <div className="border-b-2 border-grid bg-surface/40">
      <div className="ticker-mask overflow-hidden">
        <div className="flex w-max animate-ticker gap-10 px-6 py-3 font-mono text-xs">
          {row.map((it, i) => (
            <span key={i} className="flex items-center gap-3 whitespace-nowrap">
              <span className="text-muted-foreground">{it.sym}</span>
              <span className="tabular-nums">{it.px}</span>
              <span className={it.ch.startsWith("+") ? "text-signal" : "text-destructive"}>{it.ch}</span>
              <span className="text-muted-foreground/50">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}