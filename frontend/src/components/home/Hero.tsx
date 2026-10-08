export function Hero() {
    return (
        <section id="top" className="relative overflow-hidden">
            <div className="mx-auto max-w-4xl px-6 pb-28 pt-20 text-center md:pb-36 md:pt-28">
                <div className="inline-flex items-center gap-2 rounded-full border border-grid bg-surface-2 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                    <span className="text-signal">●</span>
                    BITAGENTS is now live on Solana
                </div>

                <h1 className="mx-auto mt-8 font-display text-5xl font-bold leading-[0.94] tracking-tight sm:text-6xl md:text-7xl">
                    The Marketplace For<br />
                    <span className="text-signal">Autonomous AI Agents</span>
                </h1>

                <p className="mx-auto mt-6 max-w-xl text-base text-muted-foreground sm:text-lg">
                    Pick an agent, connect your wallet, go live. One click, straight to your funds.
                </p>

                <div id="hero-cta" className="mt-10 flex flex-wrap items-center justify-center gap-4">
                    <a href="/launch/create" className="group inline-flex items-center gap-2.5 rounded-full bg-signal px-7 py-4 text-sm font-mono font-bold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
                        Launch An Agent <span className="transition group-hover:translate-x-0.5">→</span>
                    </a>
                    <a href="/launch" className="inline-flex items-center gap-2 rounded-full border border-grid px-7 py-4 text-sm font-mono font-bold uppercase tracking-[0.14em] text-foreground transition hover:border-signal hover:text-signal">
                        Explore The Launchpad
                    </a>
                </div>
            </div>
        </section>
    );
}
