import { nowIso, type DcaPlan } from "@bitagents/shared";
import { dcaConfig } from "@/server/dca/config";
import { rebuildPlanFromDraft, type PlanContext } from "@/server/dca/plan";
import { createPlan, listPlansByWallet } from "@/server/dca/store";
import { createJupiterRecurringOrder } from "@/server/dca/jupiter";
import { firstExecutionAt } from "@/server/dca/scheduler";
import { agentWalletGate, ensureAgentWallet, validateAgentWalletCaps } from "@/server/dca/agentWallet";
import { parseNetwork, requirePublicKey } from "@/server/validation";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const wallet = url.searchParams.get("wallet");
  if (!wallet) return Response.json({ plans: [] });
  const plans = await listPlansByWallet(wallet);
  return Response.json({ plans });
}

function coerceDraft(raw: unknown): DcaPlan {
  if (!raw || typeof raw !== "object") throw new Error("plan is required.");
  return raw as DcaPlan;
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as Record<string, unknown>;
    const draft = coerceDraft(body.plan);
    const walletAddress = requirePublicKey(body.walletAddress, "wallet address");
    const network = parseNetwork(body.network);
    const config = dcaConfig();
    const requestedAgentWallet = body.executionMode === "agent_wallet" || draft.executionMode === "agent_wallet";

    const ctx: PlanContext = {
      userWallet: walletAddress,
      network,
      enableMainnetDca: config.enableMainnetDca,
      executionMode: requestedAgentWallet ? "agent_wallet" : undefined
    };

    if (requestedAgentWallet) {
      const gate = agentWalletGate(walletAddress, network);
      if (!gate.enabled) {
        return Response.json({ ok: false, error: gate.reason }, { status: 403 });
      }
      const caps = validateAgentWalletCaps(
        draft.totalInputAmountUi,
        draft.numberOfOrders,
        draft.intervalSeconds,
        gate.caps
      );
      if (!caps.ok) return Response.json({ ok: false, error: caps.error }, { status: 400 });
    }

    const assembled = rebuildPlanFromDraft(draft, ctx);
    if (!assembled.ok) {
      return Response.json({ ok: false, clarification: assembled.clarification }, { status: 400 });
    }
    const plan = assembled.plan;

    if (plan.executionMode === "jupiter_recurring") {
      if (!config.enableMainnetDca) {
        return Response.json(
          { ok: false, error: "Mainnet DCA is disabled on this deployment." },
          { status: 403 }
        );
      }
      const created = await createJupiterRecurringOrder({
        user: walletAddress,
        inputMint: plan.inputMint,
        outputMint: plan.outputMint,
        inputDecimals: plan.inputDecimals,
        totalInputAmountUi: plan.totalInputAmountUi,
        numberOfOrders: plan.numberOfOrders,
        intervalSeconds: plan.intervalSeconds,
        startAt: plan.startAt
      });

      if (!created.ok) {
        // Keep the (unsaved) draft so the user can adjust size or switch modes.
        return Response.json({
          ok: false,
          jupiterError: created.error,
          minOrder: Boolean(created.minOrder),
          plan
        });
      }

      plan.status = "creating";
      plan.jupiterRequestId = created.requestId;
      await createPlan(plan);
      return Response.json({
        ok: true,
        plan,
        transaction: created.transaction,
        requestId: created.requestId,
        mode: "jupiter_recurring"
      });
    }

    if (plan.executionMode === "agent_wallet") {
      const stored = await ensureAgentWallet(walletAddress, network);
      plan.agentWalletAddress = stored.publicKey;
      plan.status = "active";
      plan.nextExecutionAt = firstExecutionAt(plan);
      await createPlan(plan);
      return Response.json({
        ok: true,
        plan,
        depositAddress: stored.publicKey,
        mode: "agent_wallet"
      });
    }

    // Devnet Demo Mode — activate immediately, scheduler simulates executions.
    plan.status = "active";
    plan.nextExecutionAt = firstExecutionAt(plan);
    plan.updatedAt = nowIso();
    await createPlan(plan);
    return Response.json({ ok: true, plan, mode: "devnet_demo" });
  } catch (error) {
    return Response.json({ ok: false, error: (error as Error).message }, { status: 400 });
  }
}
