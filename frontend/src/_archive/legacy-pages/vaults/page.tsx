import type { Metadata } from "next";
import Link from "next/link";
import { AppShell, Panel } from "@/components/AppShell";

export const metadata: Metadata = {
    title: "Vault Marketplace - ComputeVault",
    description:
        "Fund AI trading vaults that consume compute and distribute returns.",
};

type Vault = {
    id: number;
    name: string;
    tp: number;
    sl: number;
    tvl: number;
    perf: number;
    tone: "signal" | "warn";
};

const vaults: Vault[] = [
    {
        id: 1,
        name: "Conservative Vault",
        tp: 5,
        sl: 5,
        tvl: 20000,
        perf: 3.4,
        tone: "signal",
    },
    {
        id: 2,
        name: "Balanced Vault",
        tp: 10,
        sl: 5,
        tvl: 64200,
        perf: 6.8,
        tone: "signal",
    },
    {
        id: 3,
        name: "Growth Vault",
        tp: 20,
        sl: 5,
        tvl: 128400,
        perf: 14.2,
        tone: "warn",
    },
    {
        id: 4,
        name: "High Risk Vault",
        tp: 40,
        sl: 5,
        tvl: 92800,
        perf: -4.1,
        tone: "warn",
    },
];

export default function VaultsPage() {
    return (
        <AppShell
            title="Vault Marketplace"
            subtitle="Investor capital → AI agents → compute demand → yield."
        >
            <div className="grid gap-6 md:grid-cols-2">
                {vaults.map((vault) => (
                    <Panel
                        key={vault.id}
                        title={`// ${vault.name}`}
                        action={
                            <span
                                className={`font-mono text-[10px] ${vault.perf >= 0
                                    ? "text-signal"
                                    : "text-destructive"
                                    }`}
                            >
                                {vault.perf >= 0 ? "+" : ""}
                                {vault.perf}%
                            </span>
                        }
                    >
                        <div className="grid grid-cols-3 gap-px bg-[color:var(--border)]">
                            <Cell k="TP" v={`${vault.tp}%`} accent="signal" />
                            <Cell k="SL" v={`${vault.sl}%`} accent="warn" />
                            <Cell
                                k="TVL"
                                v={`$${vault.tvl.toLocaleString()}`}
                            />
                        </div>

                        <div className="mt-4 flex items-center justify-between">
                            <div>
                                <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                                    30d Performance
                                </div>

                                <div
                                    className={`mt-1 font-display text-2xl font-bold tabular-nums ${vault.perf >= 0
                                        ? "text-signal"
                                        : "text-destructive"
                                        }`}
                                >
                                    {vault.perf >= 0 ? "+" : ""}
                                    {vault.perf}%
                                </div>
                            </div>

                            <div className="flex gap-2">
                                <Link
                                    href={`/vault/${vault.id}`}
                                    className="border border-grid px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground transition hover:border-signal hover:text-foreground"
                                >
                                    Details
                                </Link>

                                <button className="bg-signal px-4 py-2 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-primary-foreground transition hover:opacity-90">
                                    Invest →
                                </button>
                            </div>
                        </div>
                    </Panel>
                ))}
            </div>
        </AppShell>
    );
}

type CellProps = {
    k: string;
    v: string;
    accent?: "signal" | "warn";
};

function Cell({ k, v, accent }: CellProps) {
    return (
        <div className="bg-background p-3">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {k}
            </div>

            <div
                className={`mt-1 font-display text-base font-semibold tabular-nums ${accent === "signal"
                    ? "text-signal"
                    : accent === "warn"
                        ? "text-warn"
                        : ""
                    }`}
            >
                {v}
            </div>
        </div>
    );
}