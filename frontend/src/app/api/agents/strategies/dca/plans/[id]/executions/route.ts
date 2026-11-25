import { NextResponse } from "next/server";
import { getAuthToken, proxyStrategyPlanExecutions } from "@/server/agentsApiProxy";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyStrategyPlanExecutions("dca", id, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json({ error: "Cannot reach the agent API", detail }, { status: 503 });
  }
}
