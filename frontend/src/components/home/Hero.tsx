export function Hero() {
    return (
        <section id="top" className="relative overflow-hidden border-b border-grid">
            <div className="mx-auto grid max-w-7xl gap-12 px-6 py-20 md:py-28 lg:grid-cols-[1.15fr_1fr] lg:items-center">
                <div>
                    <div className="inline-flex items-center gap-2 border border-grid bg-surface/60 px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.2em] text-muted-foreground">
                        <span className="h-1.5 w-1.5 rounded-full bg-signal animate-pulse-dot" />
                        Live · Solana Devnet · BIT Agents online
                    </div>
                    <h1 className="mt-6 font-display text-5xl font-bold leading-[0.95] tracking-tight md:text-6xl lg:text-7xl">
                        AI agents powered by <span className="text-signal">decentralized compute</span>.
                    </h1>
                    <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
                        BIT Agents lets users run specialized agents for wallet monitoring, research, automation, and on-chain workflows - powered by a decentralized compute network.
                    </p>
                    <div id="hero-cta" className="mt-10 flex flex-wrap gap-3">
                        <a href="/dashboard" className="group inline-flex items-center gap-2 bg-signal px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-primary-foreground transition hover:opacity-90">
                            Launch App <span className="transition group-hover:translate-x-0.5">→</span>
                        </a>
                        <a href="/provider" className="inline-flex items-center gap-2 border border-grid bg-surface/40 px-5 py-3 text-sm font-mono font-semibold uppercase tracking-[0.14em] text-foreground transition hover:border-signal">
                            Register Compute
                        </a>
                    </div>
                    <dl className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-grid pt-8">
                        {[
                            ["$0.42", "cGPU index"],
                            ["18.4k", "GPU-hrs minted"],
                            ["6.2%", "30d vault APY"],
                        ].map(([v, k]) => (
                            <div key={k}>
                                <dt className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{k}</dt>
                                <dd className="mt-1 font-display text-2xl font-bold tabular-nums">{v}</dd>
                            </div>
                        ))}
                    </dl>
                </div>
                <HeroPanel />
            </div>
        </section>
    );
}

function HeroPanel() {
    const orders = [
        { side: "BID", px: "0.412", sz: "1,200", agent: "alpha-7" },
        { side: "ASK", px: "0.418", sz: "  860", agent: "neon-vault" },
        { side: "BID", px: "0.409", sz: "2,400", agent: "delta-3" },
        { side: "ASK", px: "0.421", sz: "  420", agent: "h100-pool-a" },
        { side: "BID", px: "0.405", sz: "  980", agent: "growth-vault" },
        { side: "ASK", px: "0.424", sz: "3,150", agent: "h100-pool-b" },
    ];
    return (
        <div className="relative">
            <div className="absolute -inset-6 -z-10 opacity-60 blur-3xl"
                style={{ background: "radial-gradient(60% 50% at 60% 40%, rgba(215, 101, 69, 0.22), transparent 70%)" }} />
            <div className="border border-grid bg-surface/80 backdrop-blur">
                <div className="flex items-center justify-between border-b border-grid px-4 py-2.5">
                    <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                        <span className="h-1.5 w-1.5 rounded-full bg-signal animate-pulse-dot" />
                        cGPU / USDC · orderbook
                    </div>
                    <div className="font-mono text-[10px] text-muted-foreground">BLOCK 284,193,402</div>
                </div>
                <div className="grid grid-cols-[60px_1fr_1fr_1fr] gap-2 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    <span>Side</span><span>Price</span><span>Size</span><span>Counterparty</span>
                </div>
                <ul className="divide-y divide-[color:var(--border)]">
                    {orders.map((o, i) => (
                        <li key={i} className="grid grid-cols-[60px_1fr_1fr_1fr] items-center gap-2 px-4 py-2.5 font-mono text-sm tabular-nums">
                            <span className={o.side === "BID" ? "text-signal" : "text-warn"}>{o.side}</span>
                            <span>{o.px}</span>
                            <span className="text-muted-foreground">{o.sz}</span>
                            <span className="truncate text-muted-foreground">{o.agent}</span>
                        </li>
                    ))}
                </ul>
                <div className="grid grid-cols-3 border-t border-grid">
                    {[
                        ["Mid", "0.4150"],
                        ["24h Vol", "84.2k"],
                        ["Open Int.", "1.92M"],
                    ].map(([k, v]) => (
                        <div key={k} className="border-r border-grid px-4 py-3 last:border-r-0">
                            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{k}</div>
                            <div className="mt-1 font-display text-base font-semibold tabular-nums">{v}</div>
                        </div>
                    ))}
                </div>
            </div>
            <div className="mt-3 flex items-center justify-between border border-grid bg-surface/60 px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
                <span>↳ AGENT <span className="text-foreground">growth-vault</span> consumed <span className="text-signal">42 cGPU</span></span>
                <span>3s ago</span>
            </div>
        </div>
    );
}
