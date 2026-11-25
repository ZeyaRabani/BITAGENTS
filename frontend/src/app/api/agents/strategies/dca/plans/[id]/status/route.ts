import { NextResponse } from "next/server";
import { getAuthToken, proxyStrategyPlanStatus } from "@/server/agentsApiProxy";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: { action?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (!body.action) {
    return NextResponse.json({ error: "action is required" }, { status: 400 });
  }
  try {
    const res = await proxyStrategyPlanStatus("dca", id, body.action, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json({ error: "Cannot reach the agent API", detail }, { status: 503 });
  }
}
