export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden">
      <div className="relative mx-auto flex max-w-4xl flex-col items-center px-6 py-16 text-center md:py-24">
        <div className="inline-flex items-center rounded-full border border-signal/50 bg-signal/10 px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-signal">
          BIT Agents is now live on Solana
        </div>
        <h1 className="mt-8 font-display text-5xl font-bold leading-[0.95] tracking-tight md:text-6xl lg:text-7xl">
          The Marketplace For{" "}
          <span className="text-signal">Autonomous AI Agents</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
          Pick an agent, connect your wallet, go live. One click, straight to your funds.
        </p>
        <div id="hero-cta" className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <a
            href="/agents"
            className="group inline-flex items-center gap-2 rounded-full border border-signal bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90"
          >
            Launch an agent <span className="transition group-hover:translate-x-0.5">→</span>
          </a>
          <a
            href="/agents/launch"
            className="inline-flex items-center gap-2 rounded-full border border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal"
          >
            Explore the launchpad
          </a>
        </div>
      </div>
    </section>
  );
}
