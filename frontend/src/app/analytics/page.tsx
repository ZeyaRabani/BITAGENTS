import type { Metadata } from "next";
import { AppShell, Panel, Stat } from "@/components/AppShell";

export const metadata: Metadata = {
    title: "Marketplace Analytics - BITAGENTS",
    description:
        "Live agent activity, task volume, deployments, and marketplace settlement across the BITAGENTS protocol.",
};

const taskVolume = [820, 940, 1100, 1280, 1450, 1620, 1780, 1950, 2100, 2280, 2410, 2640];
const deployments = [2, 3, 4, 5, 6, 8, 9, 11, 13, 16, 18, 22];
const completions = [91, 92, 93, 94, 94, 95, 96, 96, 97, 97, 98, 99];

export default function AnalyticsPage() {
    return (
        <AppShell
            title="Marketplace Analytics"
            subtitle="Real-time view of the AI agent marketplace. Tasks, deployments, and settlement."
        >
            <div className="grid gap-4 md:grid-cols-4">
                <Stat label="Live Agents" value="1" accent="signal" />
                <Stat label="Tasks · 24h" value="102" accent="warn" />
                <Stat label="Marketplace Volume" value="$42,800" />
                <Stat label="Task Success Rate" value="98.4%" accent="signal" />
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-2">
                <Panel title="Agent Tasks · 24h Volume">
                    <Chart data={taskVolume} color="var(--signal)" gradientId="tasks" />
                </Panel>

                <Panel title="New Agent Deployments">
                    <Chart data={deployments} color="var(--warn)" gradientId="deployments" />
                </Panel>

                <Panel title="Task Completion Rate · 30d">
                    <Chart data={completions} color="var(--signal)" gradientId="completions" />
                </Panel>

                <Panel title="Marketplace Settlement">
                    <div className="space-y-5 py-2">
                        <Split label="Agent developers" pct={55} value="$23,540" />
                        <Split label="Task runners" pct={35} value="$14,980" />
                        <Split label="Protocol" pct={10} value="$4,280" />
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

function Chart({ data, color, gradientId }: ChartProps) {
    const width = 600;
    const height = 180;
    const padding = 8;

    const max = Math.max(...data);
    const step = (width - padding * 2) / (data.length - 1);

    const points = data
        .map(
            (value, index) =>
                `${padding + index * step},${height - padding - (value / max) * (height - padding * 2)}`
        )
        .join(" ");

    const area = `${padding},${height - padding} ${points} ${width - padding},${height - padding}`;

    return (
        <svg viewBox={`0 0 ${width} ${height}`} className="h-44 w-full" preserveAspectRatio="none">
            <defs>
                <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity="0.35" />
                    <stop offset="100%" stopColor={color} stopOpacity="0" />
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

            <polygon points={area} fill={`url(#${gradientId})`} />
            <polyline points={points} fill="none" stroke={color} strokeWidth="2" />

            {data.map((value, index) => (
                <circle
                    key={index}
                    cx={padding + index * step}
                    cy={height - padding - (value / max) * (height - padding * 2)}
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

function Split({ label, pct, value }: SplitProps) {
    return (
        <div>
            <div className="flex justify-between font-mono text-xs">
                <span className="text-muted-foreground">{label}</span>
                <span className="tabular-nums">
                    <span className="text-signal">{pct}%</span> · {value}
                </span>
            </div>
            <div className="mt-1.5 h-2 w-full bg-surface-2">
                <div className="h-full bg-signal transition-all duration-500" style={{ width: `${pct}%` }} />
            </div>
        </div>
    );
}
