import { notFound } from "next/navigation";
import { Bell } from "lucide-react";
import { CustomAgentChat } from "@/components/agents/CustomAgentChat";
import type { LaunchedAgentRecord } from "@/lib/launchpadBuilderClient";
import { proxyGetLaunchedAgent } from "@/server/agentsApiProxy";

async function fetchAgent(id: string): Promise<LaunchedAgentRecord | null> {
  try {
    const res = await proxyGetLaunchedAgent(id);
    if (!res.ok) return null;
    return (await res.json()) as LaunchedAgentRecord;
  } catch {
    return null;
  }
}

export default async function CustomAgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const agent = await fetchAgent(id);
  if (!agent) notFound();

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <div className="mb-8 border-b border-grid pb-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex h-12 w-12 items-center justify-center border border-grid bg-surface/40 text-signal">
            <Bell size={22} strokeWidth={1.75} />
          </div>
          {agent.status === "testing" && (
            <span className="border border-warn/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-warn">
              Testing
            </span>
          )}
        </div>
        <h1 className="mt-4 font-display text-3xl font-bold leading-tight md:text-4xl">
          {agent.name ?? "Untitled agent"}
        </h1>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {agent.category ?? "Uncategorized"}
        </p>
        <p className="mt-3 max-w-xl text-sm text-muted-foreground">{agent.description}</p>
      </div>

      <CustomAgentChat agent={agent} />
    </div>
  );
}
