import { makeExplorerTxUrl } from "@bitagents/shared";
import { executeJupiterRecurringOrder } from "@/server/dca/jupiter";
import { getPlan, logError, updatePlan } from "@/server/dca/store";
import { firstExecutionAt } from "@/server/dca/scheduler";
import { requireString } from "@/server/validation";

export const runtime = "nodejs";

// Submit a user-signed Jupiter Recurring transaction. This activates the
// recurring order on mainnet; Jupiter's keepers then execute the schedule.
export async function POST(request: Request, { params }: { params: { id: string } }) {
  try {
    const plan = await getPlan(params.id);
    if (!plan) return Response.json({ ok: false, error: "plan not found." }, { status: 404 });
    if (plan.executionMode !== "jupiter_recurring") {
      return Response.json({ ok: false, error: "This plan is not a Jupiter Recurring order." }, { status: 400 });
    }

    const body = (await request.json()) as Record<string, unknown>;
    const signedTransaction = requireString(body.signedTransaction, "signed transaction", 8000);
    const requestId = requireString(body.requestId ?? plan.jupiterRequestId, "request id", 200);

    const result = await executeJupiterRecurringOrder(requestId, signedTransaction);
    if (result.status !== "Success") {
      await updatePlan(plan.id, { status: "failed", error: result.error ?? "Execution failed." });
      await logError("dca.execute", result.error ?? "execute failed");
      return Response.json({ ok: false, error: result.error ?? "Execution failed." });
    }

    const updated = await updatePlan(plan.id, {
      status: "active",
      jupiterOrderAccount: result.order,
      createSignature: result.signature,
      nextExecutionAt: firstExecutionAt(plan)
    });

    return Response.json({
      ok: true,
      plan: updated,
      signature: result.signature,
      orderAccount: result.order,
      explorerUrl: result.signature ? makeExplorerTxUrl(result.signature, "mainnet") : null
    });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
