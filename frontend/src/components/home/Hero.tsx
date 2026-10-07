export function Hero() {
    return (
        <section id="top" className="relative overflow-hidden">
            <div className="mx-auto max-w-7xl px-6 py-20 md:py-28">
                <h1 className="max-w-4xl font-display text-2xl font-bold leading-[0.95] tracking-tight md:text-3xl lg:text-4xl">
                    The Marketplace For <span className="text-signal">Autonomous AI Agents</span>
                </h1>
                <div id="hero-cta" className="mt-12 flex flex-wrap gap-4">
                    <a href="/launch/create" className="group inline-flex items-center gap-2 bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
                        Launch An Agent <span className="transition group-hover:translate-x-0.5">→</span>
                    </a>
                    <a href="/launch" className="inline-flex items-center gap-2 border-2 border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal">
                        Explore The Launchpad
                    </a>
                </div>
            </div>
        </section>
    );
}
