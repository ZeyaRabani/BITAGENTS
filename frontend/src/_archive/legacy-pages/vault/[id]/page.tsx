import type { Metadata } from "next";
import Link from "next/link";
import { AppShell, Panel, Stat } from "@/components/AppShell";

type PageProps = {
    params: Promise<{
        id: string;
    }>;
};

const VAULT_MAP: Record<
    string,
    {
        name: string;
        tp: number;
        sl: number;
    }
> = {
    "1": { name: "Conservative Vault", tp: 5, sl: 5 },
    "2": { name: "Balanced Vault", tp: 10, sl: 5 },
    "3": { name: "Growth Vault", tp: 20, sl: 5 },
    "4": { name: "High Risk Vault", tp: 40, sl: 5 },
};

const activity = [
    {
        t: "12s",
        title: "SOL Buy Signal",
        detail: "agent · alpha-7 · 8 cGPU burned",
        tone: "signal",
    },
    {
        t: "1m",
        title: "BONK Position Opened",
        detail: "size 12,400 · entry 0.0000231",
        tone: "signal",
    },
    {
        t: "4m",
        title: "JUP Rebalanced",
        detail: "+2.4% allocation shift",
        tone: "warn",
    },
    {
        t: "9m",
        title: "Stop check · ETH",
        detail: "no action · within band",
        tone: "muted",
    },
    {
        t: "14m",
        title: "Compute Purchase",
        detail: "buy 80 cGPU @ 0.413",
        tone: "signal",
    },
] as const;

export async function generateMetadata({
    params,
}: PageProps): Promise<Metadata> {
    const { id } = await params;

    const vault = VAULT_MAP[id] ?? {
        name: "Vault",
        tp: 10,
        sl: 5,
    };

    return {
        title: `${vault.name} — ComputeVault`,
        description:
            "See how a vault buys, consumes, and burns compute to generate yield.",
    };
}

// Optional: pre-render known vault pages
export async function generateStaticParams() {
    return Object.keys(VAULT_MAP).map((id) => ({
        id,
    }));
}

export default async function VaultDetailPage({
    params,
}: PageProps) {
    const { id } = await params;

    const vault = VAULT_MAP[id] ?? {
        name: "Vault",
        tp: 10,
        sl: 5,
    };

    return (
        <AppShell
            title={vault.name}
            subtitle={`Vault → Buys Compute → Consumes Compute · TP ${vault.tp}% · SL ${vault.sl}%`}
        >
            <div className="mb-4">
                <Link
                    href="/vaults"
                    className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground"
                >
                    ← All Vaults
                </Link>
            </div>

            <div className="grid gap-4 md:grid-cols-4">
                <Stat label="TVL" value="$128,400" />
                <Stat
                    label="Current Profit"
                    value="+$17,820"
                    accent="signal"
                />
                <Stat
                    label="Compute Consumed"
                    value="120 cGPU"
                    accent="warn"
                />
                <Stat label="Trades Executed" value="284" />
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
                <Panel title="// Compute Usage">
                    <div className="space-y-4">
                        <Bar
                            label="Bought"
                            value={200}
                            max={200}
                            suffix="cGPU"
                            tone="signal"
                        />

                        <Bar
                            label="Used"
                            value={120}
                            max={200}
                            suffix="cGPU"
                            tone="warn"
                        />

                        <Bar
                            label="Remaining"
                            value={80}
                            max={200}
                            suffix="cGPU"
                            tone="muted"
                        />

                        <div className="mt-6 border border-grid bg-background p-4 font-mono text-[11px] leading-relaxed text-muted-foreground">
                            <div className="text-foreground">flow</div>

                            <div className="mt-2">
                                vault.deposit($USDC)
                            </div>

                            <div className="text-signal">
                                ↓ buys 200 cGPU @ 0.415
                            </div>

                            <div>agent.consume(120 cGPU)</div>

                            <div className="text-warn">
                                ↓ executes 284 trades · +13.8% PnL
                            </div>

                            <div className="text-signal">
                                → settle to depositors
                            </div>
                        </div>
                    </div>
                </Panel>

                <Panel title="// Strategy Activity">
                    <ul className="divide-y divide-[color:var(--border)]">
                        {activity.map((item, index) => (
                            <li
                                key={index}
                                className="flex items-start gap-4 py-3"
                            >
                                <span
                                    className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
                                    style={{
                                        background:
                                            item.tone === "signal"
                                                ? "var(--signal)"
                                                : item.tone === "warn"
                                                    ? "var(--warn)"
                                                    : "oklch(0.5 0 0)",
                                    }}
                                />

                                <div className="flex-1">
                                    <div className="flex items-baseline justify-between gap-2">
                                        <span className="font-display text-sm font-semibold">
                                            {item.title}
                                        </span>

                                        <span className="font-mono text-[10px] text-muted-foreground">
                                            {item.t} ago
                                        </span>
                                    </div>

                                    <div className="mt-0.5 font-mono text-xs text-muted-foreground">
                                        {item.detail}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ul>
                </Panel>
            </div>
        </AppShell>
    );
}

type BarProps = {
    label: string;
    value: number;
    max: number;
    suffix: string;
    tone: "signal" | "warn" | "muted";
};

function Bar({
    label,
    value,
    max,
    suffix,
    tone,
}: BarProps) {
    const pct = (value / max) * 100;

    const color =
        tone === "signal"
            ? "var(--signal)"
            : tone === "warn"
                ? "var(--warn)"
                : "oklch(0.5 0 0)";

    return (
        <div>
            <div className="flex justify-between font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                <span>{label}</span>

                <span className="tabular-nums text-foreground">
                    {value} {suffix}
                </span>
            </div>

            <div className="mt-1.5 h-2 w-full bg-surface-2">
                <div
                    className="h-full transition-all"
                    style={{
                        width: `${pct}%`,
                        background: color,
                    }}
                />
            </div>
        </div>
    );
}