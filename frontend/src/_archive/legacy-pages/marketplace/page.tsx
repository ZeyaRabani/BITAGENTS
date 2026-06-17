import Link from "next/link";
import { AppShell, Panel, Stat } from "@/components/AppShell";
import { getListings } from "@/lib/marketplaceStore";

const buys = [
    { px: 0.412, sz: 1200, by: "alpha-7" },
    { px: 0.409, sz: 2400, by: "delta-3" },
    { px: 0.405, sz: 980, by: "growth-vault" },
    { px: 0.401, sz: 640, by: "neon-vault" },
];

const sells = [
    { px: 0.418, sz: 860, by: "h100-pool-a" },
    { px: 0.421, sz: 420, by: "GPUFarm01" },
    { px: 0.424, sz: 3150, by: "h100-pool-b" },
    { px: 0.43, sz: 1100, by: "ColoMesh" },
];

export default function MarketplacePage() {
    const listings = getListings();

    return (
        <AppShell
            title="Compute Marketplace"
            subtitle="Live orderbook for tokenized GPU-hours. Buy compute · settle on Solana."
        >
            <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
                <Panel
                    title="// Compute Listings"
                    action={
                        <span className="font-mono text-[10px] text-muted-foreground">
                            {listings.length} active
                        </span>
                    }
                >
                    <table className="w-full font-mono text-sm">
                        <thead>
                            <tr className="text-left text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                                <th className="py-2">Provider</th>
                                <th>GPU</th>
                                <th>Hours</th>
                                <th>Price</th>
                                <th />
                            </tr>
                        </thead>

                        <tbody className="divide-y divide-[color:var(--border)]">
                            {listings.map((listing) => (
                                <tr key={`${listing.provider}-${listing.gpu}`} className="hover:bg-surface/60">
                                    <td className="py-3">{listing.provider}</td>
                                    <td className="text-warn">{listing.gpu}</td>
                                    <td className="tabular-nums">{listing.hours.toLocaleString()}</td>
                                    <td className="text-signal tabular-nums">
                                        ${listing.price.toFixed(2)}
                                    </td>
                                    <td className="text-right">
                                        <button className="border border-grid px-3 py-1.5 text-[10px] uppercase tracking-[0.16em] transition hover:border-signal hover:text-signal">
                                            Buy Compute
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Panel>

                <Panel title="// cGPU Token">
                    <div className="space-y-4">
                        <div>
                            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                                Current Price
                            </div>

                            <div className="mt-1 font-display text-4xl font-bold tabular-nums text-signal">
                                $0.415
                            </div>

                            <div className="mt-1 font-mono text-xs text-signal">
                                +2.4% / 24h
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-px bg-[color:var(--border)]">
                            <div className="bg-background p-3">
                                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                                    24h Volume
                                </div>
                                <div className="mt-1 font-display text-lg font-semibold tabular-nums">
                                    84.2k
                                </div>
                            </div>

                            <div className="bg-background p-3">
                                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                                    Supply
                                </div>
                                <div className="mt-1 font-display text-lg font-semibold tabular-nums">
                                    1.92M
                                </div>
                            </div>
                        </div>

                        <Link
                            href="/vaults"
                            className="block w-full bg-signal py-2.5 text-center font-mono text-xs font-semibold uppercase tracking-[0.16em] text-primary-foreground transition hover:opacity-90"
                        >
                            Allocate via Vault →
                        </Link>
                    </div>
                </Panel>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <Panel title="// Buy Orders">
                    <ul className="divide-y divide-[color:var(--border)] font-mono text-sm">
                        {buys.map((order, index) => (
                            <li
                                key={index}
                                className="grid grid-cols-[1fr_1fr_1.5fr] gap-2 py-2.5 tabular-nums"
                            >
                                <span className="text-signal">{order.px.toFixed(3)}</span>
                                <span>{order.sz.toLocaleString()}</span>
                                <span className="truncate text-muted-foreground">{order.by}</span>
                            </li>
                        ))}
                    </ul>
                </Panel>

                <Panel title="// Sell Orders">
                    <ul className="divide-y divide-[color:var(--border)] font-mono text-sm">
                        {sells.map((order, index) => (
                            <li
                                key={index}
                                className="grid grid-cols-[1fr_1fr_1.5fr] gap-2 py-2.5 tabular-nums"
                            >
                                <span className="text-warn">{order.px.toFixed(3)}</span>
                                <span>{order.sz.toLocaleString()}</span>
                                <span className="truncate text-muted-foreground">{order.by}</span>
                            </li>
                        ))}
                    </ul>
                </Panel>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-4">
                <Stat label="Mid Price" value="0.4150" accent="signal" />
                <Stat label="Spread" value="0.006" />
                <Stat label="Open Interest" value="1.92M" />
                <Stat label="24h High" value="0.428" accent="warn" />
            </div>
        </AppShell>
    );
}
