import { cancelJupiterRecurringOrder } from "@/server/dca/jupiter";
import { getPlan, updatePlan } from "@/server/dca/store";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: { id: string } }) {
  try {
    const plan = await getPlan(params.id);
    if (!plan) return Response.json({ ok: false, error: "plan not found." }, { status: 404 });
    if (plan.status === "cancelled" || plan.status === "completed") {
      return Response.json({ ok: true, plan });
    }

    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;

    // Devnet demo + agent wallet cancel immediately (no on-chain recurring order).
    if (plan.executionMode !== "jupiter_recurring") {
      const updated = await updatePlan(plan.id, { status: "cancelled", nextExecutionAt: null });
      return Response.json({ ok: true, plan: updated });
    }

    // Jupiter Recurring: a signature means the client already sent the cancel tx.
    if (typeof body.signature === "string" && body.signature.trim().length > 0) {
      const updated = await updatePlan(plan.id, {
        status: "cancelled",
        cancelSignature: body.signature.trim(),
        nextExecutionAt: null
      });
      return Response.json({ ok: true, plan: updated });
    }

    if (!plan.jupiterOrderAccount) {
      return Response.json({ ok: false, error: "No on-chain order account to cancel yet." }, { status: 400 });
    }

    const cancel = await cancelJupiterRecurringOrder(plan.jupiterOrderAccount, plan.userWallet);
    if (!cancel.ok) {
      return Response.json({ ok: false, error: cancel.error });
    }
    // Client must sign + send this transaction, then call again with the signature.
    return Response.json({ ok: true, needsSignature: true, transaction: cancel.transaction, requestId: cancel.requestId });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
