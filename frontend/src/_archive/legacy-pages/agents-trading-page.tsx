import type { Metadata } from "next";
import { AppShell, Panel } from "@/components/AppShell";

export const metadata: Metadata = {
    title: "Agent Monitoring — ComputeVault",
    description:
        "Live monitoring of autonomous AI trading agents consuming compute.",
};

type Agent = {
    name: string;
    budget: number;
    used: number;
    status: "Running" | "Idle";
    task: string;
    strategy: string;
};

const agents: Agent[] = [
    {
        name: "Momentum Agent",
        budget: 50,
        used: 32,
        status: "Running",
        task: "Analyzing SOL",
        strategy: "trend-follow",
    },
    {
        name: "Meme Rotation Agent",
        budget: 20,
        used: 14,
        status: "Running",
        task: "Scanning BONK, WIF, POPCAT",
        strategy: "rotation",
    },
    {
        name: "Mean Reversion Agent",
        budget: 35,
        used: 28,
        status: "Running",
        task: "Rebalancing JUP",
        strategy: "mean-revert",
    },
    {
        name: "Arbitrage Agent",
        budget: 45,
        used: 11,
        status: "Idle",
        task: "Waiting for spread > 0.4%",
        strategy: "cross-dex",
    },
];

export default function AgentsPage() {
    return (
        <AppShell
            title="Agent Monitoring"
            subtitle="The demand side. Every signal, every trade burns cGPU."
        >
            <div className="grid gap-6 md:grid-cols-2">
                {agents.map((agent) => {
                    const pct = (agent.used / agent.budget) * 100;
                    const running = agent.status === "Running";

                    return (
                        <Panel
                            key={agent.name}
                            title={`// ${agent.strategy}`}
                            action={
                                <span
                                    className={`inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] ${running
                                            ? "text-signal"
                                            : "text-muted-foreground"
                                        }`}
                                >
                                    <span
                                        className={`h-1.5 w-1.5 rounded-full ${running
                                                ? "bg-signal animate-pulse-dot"
                                                : "bg-muted-foreground"
                                            }`}
                                    />
                                    {agent.status}
                                </span>
                            }
                        >
                            <div className="font-display text-xl font-bold">
                                {agent.name}
                            </div>

                            <div className="mt-1 font-mono text-xs text-muted-foreground">
                                ↳ {agent.task}
                            </div>

                            <div className="mt-5">
                                <div className="flex justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                                    <span>Compute Budget</span>

                                    <span className="tabular-nums text-foreground">
                                        {agent.used} / {agent.budget} cGPU
                                    </span>
                                </div>

                                <div className="mt-1.5 h-2 w-full bg-surface-2">
                                    <div
                                        className="h-full bg-signal transition-all duration-500"
                                        style={{
                                            width: `${pct}%`,
                                        }}
                                    />
                                </div>
                            </div>
                        </Panel>
                    );
                })}
            </div>
        </AppShell>
    );
}