import { nowIso, type AgentTask } from "@bitagents/shared";
import { randomUUID } from "node:crypto";
import { LOCAL_PROVIDER, chooseProvider, providerPriceOrDefault, readDb, updateDb } from "@/server/db";
import { optionalString, parseAgentInput, parseAgentType, parseNetwork } from "@/server/validation";
import { requirePublicKey } from "@/server/validation";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const db = await readDb();
  const url = new URL(request.url);
  const requesterWallet = url.searchParams.get("requesterWallet");
  const assignedProviderWallet = url.searchParams.get("assignedProviderWallet");
  const status = url.searchParams.get("status");

  const tasks = db.tasks
    .filter((task) => !requesterWallet || task.requesterWallet === requesterWallet)
    .filter((task) => !assignedProviderWallet || task.assignedProviderWallet === assignedProviderWallet)
    .filter((task) => !status || task.status === status)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

  return Response.json({ tasks });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const type = parseAgentType(body.type);
    const input = parseAgentInput(type, body.input);
    const network = parseNetwork(body.network);
    const requesterRaw = optionalString(body.requesterWallet, "requester wallet", 80);
    const requesterWallet = requesterRaw ? requirePublicKey(requesterRaw, "requester wallet") : null;
    const free = body.free === true || requesterWallet === null;

    const task = await updateDb<AgentTask>((db) => {
      const provider = chooseProvider(db) ?? LOCAL_PROVIDER;
      const at = nowIso();
      const created: AgentTask = {
        id: randomUUID(),
        type,
        input,
        network,
        requesterWallet,
        free,
        status: "created",
        priceSol: free ? 0 : providerPriceOrDefault(provider),
        assignedProviderId: provider.id,
        assignedProviderWallet: provider.walletAddress,
        assignedProviderName: provider.name,
        createdAt: at,
        updatedAt: at,
        history: [
          {
            status: "created",
            at,
            note: free ? "Free demo task created." : "Task created, awaiting devnet payment."
          }
        ]
      };
      db.tasks.push(created);
      return created;
    });

    return Response.json({ task });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
