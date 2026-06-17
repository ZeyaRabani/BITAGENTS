import { nowIso, type AgentResult } from "@bitagents/shared";
import { LOCAL_PROVIDER, findProvider, recordStatus, updateDb } from "@/server/db";
import { runAgent } from "@/server/agents";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(_request: Request, { params }: { params: { taskId: string } }) {
  try {
    // Phase 1: lock task into the "computing" state.
    const prepared = await updateDb((db) => {
      const found = db.tasks.find((item) => item.id === params.taskId);
      if (!found) {
        throw new Error("task not found.");
      }
      if (found.status === "completed") {
        return found;
      }
      const canRun = found.free
        ? found.status === "created" || found.status === "assigned"
        : found.status === "paid" || found.status === "assigned";
      if (!canRun) {
        throw new Error(`task cannot run from status "${found.status}".`);
      }

      const provider = findProvider(db, found.assignedProviderId) ?? LOCAL_PROVIDER;
      found.assignedProviderId = provider.id;
      found.assignedProviderWallet = provider.walletAddress;
      found.assignedProviderName = provider.name;
      recordStatus(found, "assigned", `Assigned to ${provider.name}.`);
      recordStatus(found, "computing", "Provider running real computation.");
      return found;
    });

    if (prepared.status === "completed") {
      return Response.json({ task: prepared });
    }

    // Phase 2: run the real computation outside the read/write cycle.
    let result: AgentResult | undefined;
    let failure: string | undefined;
    try {
      result = await runAgent(prepared);
    } catch (error) {
      failure = (error as Error).message;
    }

    // Phase 3: persist the outcome.
    const task = await updateDb((db) => {
      const found = db.tasks.find((item) => item.id === params.taskId);
      if (!found) {
        throw new Error("task not found.");
      }

      if (!result) {
        found.error = failure ?? "Computation failed.";
        recordStatus(found, "failed", found.error);
        return found;
      }

      found.result = result;
      found.runtimeMs = result.runtimeMs;
      found.error = undefined;
      recordStatus(found, "completed", `Completed in ${result.runtimeMs}ms via ${result.engine}.`);

      const provider = db.providers.find((item) => item.id === found.assignedProviderId);
      if (provider) {
        provider.tasksCompleted += 1;
        provider.reputation = Math.min(100, provider.reputation + 1);
        provider.updatedAt = nowIso();
      }
      return found;
    });

    return Response.json({ task });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
