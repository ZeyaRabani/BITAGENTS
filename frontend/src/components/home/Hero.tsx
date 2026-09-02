export function Hero() {
    return (
        <section id="top" className="relative overflow-hidden border-b border-grid">
            <div className="mx-auto max-w-7xl px-6 py-10">
                <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-signal">
                    The Financial Operating System For AI Agents
                </div>
                <h1 className="mt-6 max-w-4xl font-display text-5xl font-bold leading-[0.95] tracking-tight md:text-6xl lg:text-7xl">
                    The Marketplace For <span className="text-signal">Autonomous AI Agents</span>.
                </h1>
                <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
                    Discover, run, and launch specialized AI agents for trading, research, and on-chain
                    automation. No code — describe what it should do, and put it to work.
                </p>
                <div id="hero-cta" className="mt-10 flex flex-wrap gap-3">
                    <a href="/launch/create" className="group inline-flex items-center gap-2 bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
                        Launch An Agent <span className="transition group-hover:translate-x-0.5">→</span>
                    </a>
                    <a href="/launch" className="inline-flex items-center gap-2 border border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal">
                        Explore The Launchpad
                    </a>
                </div>
            </div>
        </section>
    );
}
