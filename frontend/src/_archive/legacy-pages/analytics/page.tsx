import type { Metadata } from "next";
import { AppShell, Panel, Stat } from "@/components/AppShell";

export const metadata: Metadata = {
    title: "Protocol Analytics — ComputeVault",
    description:
        "Compute supply, demand, vault flows, and revenue distribution across the ComputeVault protocol.",
};

const supply = [12, 18, 22, 28, 26, 34, 40, 38, 46, 52, 58, 64];
const demand = [8, 11, 16, 20, 24, 26, 30, 36, 38, 42, 48, 55];
const vaultDemand = [4, 6, 9, 12, 14, 16, 20, 24, 28, 32, 38, 44];

export default function AnalyticsPage() {
    return (
        <AppShell
            title="Protocol Analytics"
            subtitle="Real-time view of the compute economy. Supply, demand, revenue."
        >
            <div className="grid gap-4 md:grid-cols-4">
                <Stat
                    label="GPU-Hrs Listed"
                    value="18,420"
                    accent="signal"
                />
                <Stat
                    label="cGPU Consumed"
                    value="12,184"
                    accent="warn"
                />
                <Stat label="Vault TVL" value="$305,400" />
                <Stat
                    label="Protocol Revenue"
                    value="$8,420"
                    accent="signal"
                />
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <Panel title="// Compute Supply · GPU-Hours Listed">
                    <Chart
                        data={supply}
                        color="var(--signal)"
                        gradientId="supply"
                    />
                </Panel>

                <Panel title="// Compute Demand · cGPU Consumed">
                    <Chart
                        data={demand}
                        color="var(--warn)"
                        gradientId="demand"
                    />
                </Panel>

                <Panel title="// Vault Demand · Compute Purchased by Vaults">
                    <Chart
                        data={vaultDemand}
                        color="var(--signal)"
                        gradientId="vault-demand"
                    />
                </Panel>

                <Panel title="// Revenue Distribution">
                    <div className="space-y-5 py-2">
                        <Split
                            label="Providers"
                            pct={62}
                            value="$5,220"
                        />

                        <Split
                            label="Investors"
                            pct={28}
                            value="$2,358"
                        />

                        <Split
                            label="Protocol"
                            pct={10}
                            value="$842"
                        />
                    </div>
                </Panel>
            </div>
        </AppShell>
    );
}

type ChartProps = {
    data: number[];
    color: string;
    gradientId: string;
};

function Chart({
    data,
    color,
    gradientId,
}: ChartProps) {
    const width = 600;
    const height = 180;
    const padding = 8;

    const max = Math.max(...data);

    const step =
        (width - padding * 2) / (data.length - 1);

    const points = data
        .map(
            (value, index) =>
                `${padding + index * step},${height -
                padding -
                (value / max) * (height - padding * 2)
                }`
        )
        .join(" ");

    const area = `${padding},${height - padding} ${points} ${width - padding
        },${height - padding}`;

    return (
        <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-44 w-full"
            preserveAspectRatio="none"
        >
            <defs>
                <linearGradient
                    id={gradientId}
                    x1="0"
                    x2="0"
                    y1="0"
                    y2="1"
                >
                    <stop
                        offset="0%"
                        stopColor={color}
                        stopOpacity="0.35"
                    />
                    <stop
                        offset="100%"
                        stopColor={color}
                        stopOpacity="0"
                    />
                </linearGradient>
            </defs>

            {[0.25, 0.5, 0.75].map((p) => (
                <line
                    key={p}
                    x1={padding}
                    x2={width - padding}
                    y1={height * p}
                    y2={height * p}
                    stroke="oklch(1 0 0 / 0.06)"
                    strokeDasharray="2 4"
                />
            ))}

            <polygon
                points={area}
                fill={`url(#${gradientId})`}
            />

            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth="2"
            />

            {data.map((value, index) => (
                <circle
                    key={index}
                    cx={padding + index * step}
                    cy={
                        height -
                        padding -
                        (value / max) * (height - padding * 2)
                    }
                    r="2.5"
                    fill={color}
                />
            ))}
        </svg>
    );
}

type SplitProps = {
    label: string;
    pct: number;
    value: string;
};

function Split({
    label,
    pct,
    value,
}: SplitProps) {
    return (
        <div>
            <div className="flex justify-between font-mono text-xs">
                <span className="text-muted-foreground">
                    {label}
                </span>

                <span className="tabular-nums">
                    <span className="text-signal">
                        {pct}%
                    </span>{" "}
                    · {value}
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
    );
}