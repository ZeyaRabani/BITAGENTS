import Link from "next/link";
import type { MarketplaceAgent } from "@/lib/agentsCatalog";

export function AgentDetailHeader({
  agent,
  apiOnline,
  model,
  cluster,
}: {
  agent: MarketplaceAgent;
  apiOnline?: boolean;
  model?: string;
  cluster?: string;
}) {
  return (
    <>
      <div className="mb-6 flex flex-col items-start justify-between gap-4 border-b-2 border-grid pb-6 md:flex-row md:items-end">
        <div>
          <h1 className="font-display text-3xl font-bold leading-tight md:text-4xl">{agent.name}</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            {agent.description}
          </p>
        </div>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        <Link href="/agents" className="transition hover:text-signal">
          ← Marketplace
        </Link>
        <span>/</span>
        <span className={`inline-flex items-center gap-2 ${apiOnline ? "text-signal" : "text-warn"}`}>
          <span
            className={`h-1.5 w-1.5 rounded-full ${apiOnline ? "bg-signal animate-pulse-dot" : "bg-warn"}`}
          />
          {apiOnline ? "API online" : "API offline"}
        </span>
        <span>·</span>
        <span>{model ?? agent.model ?? "-"}</span>
        <span>·</span>
        <span>{cluster ?? agent.cluster ?? "mainnet"}</span>
      </div>
    </>
  );
}
