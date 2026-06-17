import { getPlan, listExecutions } from "@/server/dca/store";
import { processDuePlans } from "@/server/dca/scheduler";

export const runtime = "nodejs";

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  // Opportunistically advance the simulated scheduler so the Devnet Demo runs
  // end-to-end even when no external cron/worker is configured. Idempotency
  // keys make this safe to call on every poll. Jupiter Recurring plans are not
  // affected (Jupiter's own keepers drive those).
  try {
    await processDuePlans();
  } catch {
    // Never fail a read because a simulation tick errored.
  }

  const plan = await getPlan(params.id);
  if (!plan) {
    return Response.json({ error: "plan not found." }, { status: 404 });
  }
  const executions = await listExecutions(plan.id);
  return Response.json({ plan, executions });
}
