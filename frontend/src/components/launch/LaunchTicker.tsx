const EVENTS = [
  { who: "7xQ2…kP3m", verb: "deployed", what: "Yield Scout", tone: "signal" },
  { who: "3nR8…vT1z", verb: "ran", what: "DCA Agent · 4 cycles", tone: "muted" },
  { who: "9wLk…hB4x", verb: "confirmed a strategy on", what: "Hedge Fund Agent", tone: "signal" },
  { who: "0xharshal", verb: "pushed an update to", what: "Yield Scout", tone: "muted" },
  { who: "jaymar", verb: "launched", what: "Floor Sniper", tone: "signal" },
  { who: "5fGm…9cQe", verb: "bonded", what: "Volume Agent pool", tone: "signal" },
  { who: "2kJp…3wXa", verb: "ran", what: "Due Diligence Agent", tone: "muted" },
];

export function LaunchTicker() {
  const row = [...EVENTS, ...EVENTS];
  return (
    <div className="border-b border-grid bg-surface/40">
      <div className="ticker-mask overflow-hidden">
        <div className="flex w-max animate-ticker gap-8 px-6 py-2.5 font-mono text-xs">
          {row.map((e, i) => (
            <span key={i} className="flex items-center gap-2 whitespace-nowrap">
              <span className={e.tone === "signal" ? "text-signal" : "text-muted-foreground"}>{e.who}</span>
              <span className="text-muted-foreground">{e.verb}</span>
              <span className="text-foreground">{e.what}</span>
              <span className="text-muted-foreground/50">·</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
