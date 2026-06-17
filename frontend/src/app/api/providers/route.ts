import { nowIso, type ComputeProvider } from "@bitagents/shared";
import { randomUUID } from "node:crypto";
import { updateDb } from "@/server/db";
import {
  optionalString,
  parseComputeType,
  parsePriceSol,
  parseProviderStatus,
  requirePublicKey,
  requireString
} from "@/server/validation";

export const runtime = "nodejs";

export async function GET() {
  const providers = await updateDb((db) =>
    [...db.providers].sort((a, b) => {
      if (a.status !== b.status) return a.status === "online" ? -1 : 1;
      return b.reputation - a.reputation;
    })
  );
  return Response.json({ providers });
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const walletAddress = requirePublicKey(body.walletAddress, "wallet address");
    const name = requireString(body.name, "provider name", 80);
    const computeType = parseComputeType(body.computeType);
    const pricePerTaskSol = parsePriceSol(body.pricePerTaskSol);
    const status = parseProviderStatus(body.status);
    const endpoint = optionalString(body.endpoint, "endpoint", 200);
    const registrationSignature = optionalString(body.registrationSignature, "signature", 200);
    const registrationMessage = optionalString(body.registrationMessage, "message", 600);

    const provider = await updateDb<ComputeProvider>((db) => {
      const existing = db.providers.find((item) => item.walletAddress === walletAddress);
      const at = nowIso();

      if (existing) {
        existing.name = name;
        existing.computeType = computeType;
        existing.pricePerTaskSol = pricePerTaskSol;
        existing.status = status;
        existing.endpoint = endpoint ?? existing.endpoint;
        existing.registrationSignature = registrationSignature ?? existing.registrationSignature;
        existing.registrationMessage = registrationMessage ?? existing.registrationMessage;
        existing.updatedAt = at;
        return existing;
      }

      const created: ComputeProvider = {
        id: randomUUID(),
        name,
        walletAddress,
        computeType,
        pricePerTaskSol,
        status,
        tasksCompleted: 0,
        reputation: 100,
        endpoint,
        registrationSignature,
        registrationMessage,
        createdAt: at,
        updatedAt: at
      };
      db.providers.push(created);
      return created;
    });

    return Response.json({ provider });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
