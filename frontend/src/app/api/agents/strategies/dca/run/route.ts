import { NextResponse } from "next/server";
import { getAuthToken, proxyStrategyRun } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: { plan_id?: string; mode?: "preview" };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (!body.plan_id) {
    return NextResponse.json({ error: "plan_id is required" }, { status: 400 });
  }
  try {
    const res = await proxyStrategyRun(
      "dca",
      { plan_id: body.plan_id, mode: body.mode ?? "preview" },
      authToken
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json({ error: "Cannot reach the agent API", detail }, { status: 503 });
  }
}
