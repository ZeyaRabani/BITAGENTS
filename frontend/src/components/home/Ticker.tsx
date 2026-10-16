import { LAUNCHED_AGENTS, formatUsd } from "@/lib/launchpadMock";

/** Virtuals' "live trade feed" pattern -- a scrolling strip proving real
 * activity is happening, instead of a static page. Pulls from the same
 * LAUNCHED_AGENTS data the Trending section uses, so it's connected to
 * real agent stats rather than disconnected placeholder copy. */
export function Ticker() {
  const items = LAUNCHED_AGENTS.map((a) => ({
    sym: a.handle,
    px: `${a.runs.toLocaleString()} runs`,
    ch: formatUsd(a.volumeUsd),
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
