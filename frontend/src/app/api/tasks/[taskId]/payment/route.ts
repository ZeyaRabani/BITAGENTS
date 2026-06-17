import { recordStatus, updateDb } from "@/server/db";
import { requirePublicKey, requireString } from "@/server/validation";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: { taskId: string } }) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const paymentSignature = requireString(body.paymentSignature, "payment signature", 120);
    const requesterWallet = requirePublicKey(body.requesterWallet, "requester wallet");

    const task = await updateDb((db) => {
      const found = db.tasks.find((item) => item.id === params.taskId);
      if (!found) {
        throw new Error("task not found.");
      }
      if (found.requesterWallet !== requesterWallet) {
        throw new Error("requester wallet does not match task owner.");
      }
      if (found.status !== "created") {
        throw new Error(`task is already ${found.status}.`);
      }

      found.paymentSignature = paymentSignature;
      recordStatus(found, "paid", "Devnet payment signature recorded.");
      return found;
    });

    return Response.json({ task });
  } catch (error) {
    return Response.json({ error: (error as Error).message }, { status: 400 });
  }
}
