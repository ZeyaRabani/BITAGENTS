const phases: { phase: string; title: string; items: string[] }[] = [
  { phase: "Phase 1", title: "Launch", items: ["BIT Agents token launch", "Holder airdrop", "Brand and marketplace setup"] },
  { phase: "Phase 2", title: "MVP", items: ["Wallet Watcher Agent", "Research Agent", "Compute Provider Worker", "Solana-based task payments"] },
  { phase: "Phase 3", title: "Marketplace", items: ["Agent task marketplace", "Provider dashboard", "Task assignment", "Compute rewards"] },
  { phase: "Phase 4", title: "Network", items: ["More agents", "Token utility integrations", "Provider staking", "Inference marketplace experiments"] },
];

export function Roadmap() {
  return (
    <section id="roadmap" className="border-b border-grid">
      <div className="mx-auto max-w-7xl px-6 py-20 md:py-28">
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">Timeline</div>
            <h2 className="mt-4 font-display text-4xl font-bold leading-tight md:text-5xl">
              Roadmap
            </h2>
          </div>
          <div className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">FY26 - FY27</div>
        </div>

        <div className="mt-12 grid gap-px bg-[color:var(--border)] border border-grid sm:grid-cols-2 lg:grid-cols-4">
          {phases.map((p) => (
            <div key={p.phase} className="bg-background p-6">
              <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">{p.phase}</div>
              <div className="mt-4 font-display text-xl font-bold">{p.title}</div>
              <ul className="mt-5 space-y-2.5 text-sm text-muted-foreground">
                {p.items.map((it) => (
                  <li key={it} className="flex items-start gap-2"><span className="mt-0.5 text-signal">✓</span> {it}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-20 border border-grid bg-surface/60 p-10 md:p-14">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">// vision</div>
          <p className="mt-4 max-w-3xl font-display text-2xl font-semibold leading-snug md:text-3xl">
            AI agents should be as accessible and composable as any other piece of crypto infrastructure. BIT Agents is the marketplace that makes it so.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href="/dashboard" className="bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
              Launch the App →
            </a>
            <a href="#product" className="border border-grid px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] transition hover:border-signal">
              Read the docs
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}