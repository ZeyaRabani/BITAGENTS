export function Hero() {
    return (
        <section id="top" className="relative overflow-hidden border-b border-grid">
            <div className="mx-auto grid max-w-7xl gap-12 px-6 py-10 lg:grid-cols-[1.15fr_1fr] lg:items-center">
                <div>
                    <h1 className="mt-6 font-display text-5xl font-bold leading-[0.95] tracking-tight md:text-6xl lg:text-7xl">
                        The Marketplace For <span className="text-signal">Autonomous AI Agents</span>.
                    </h1>
                    <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
                        BIT Agents is the on-chain marketplace where users discover, and run specialized AI agents for wallet monitoring, research, automation, and on-chain workflows.
                    </p>
                    <div id="hero-cta" className="mt-10 flex flex-wrap gap-3">
                        <a href="/agents" className="group inline-flex items-center gap-2 bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
                            Explore Agents <span className="transition group-hover:translate-x-0.5">→</span>
                        </a>
                        <a href="/signup" className="inline-flex items-center gap-2 border border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal">
                            Get notified
                        </a>
                    </div>
                    {/* <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-grid pt-8">
                        {[
                            ["48", "Live agents"],
                            ["12.4k", "Tasks executed"],
                            ["99.2%", "Uptime · 30d"],
                        ].map(([v, k]) => (
                            <div key={k}>
                                <dt className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{k}</dt>
                                <dd className="mt-1 font-display text-2xl font-bold tabular-nums">{v}</dd>
                            </div>
                        ))}
                    </dl> */}
                </div>
                {/* <HeroPanel /> */}
            </div>
        </section>
    );
}
