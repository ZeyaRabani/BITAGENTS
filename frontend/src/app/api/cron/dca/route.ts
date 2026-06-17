import { dcaConfig } from "@/server/dca/config";
import { processDuePlans } from "@/server/dca/scheduler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function authorized(request: Request): boolean {
  const secret = dcaConfig().cronSecret;
  if (!secret) return true; // no secret configured (local/dev)
  const url = new URL(request.url);
  const fromQuery = url.searchParams.get("secret");
  const header = request.headers.get("authorization");
  const fromHeader = header?.toLowerCase().startsWith("bearer ") ? header.slice(7) : header;
  const fromCustom = request.headers.get("x-cron-secret");
  return fromQuery === secret || fromHeader === secret || fromCustom === secret;
}

async function run(request: Request) {
  if (!authorized(request)) {
    return Response.json({ ok: false, error: "Unauthorized." }, { status: 401 });
  }
  const summary = await processDuePlans();
  return Response.json({ ok: true, processed: summary.processed, executions: summary.executions });
}

export async function GET(request: Request) {
  return run(request);
}

export async function POST(request: Request) {
  return run(request);
}
