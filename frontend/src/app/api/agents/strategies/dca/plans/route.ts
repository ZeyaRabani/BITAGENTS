import { NextResponse } from "next/server";
import { getAuthToken, proxyStrategyPlans } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyStrategyPlans("dca", authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json({ error: "Cannot reach the agent API", detail }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  try {
    const res = await proxyStrategyPlans("dca", authToken, { method: "POST", body });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json({ error: "Cannot reach the agent API", detail }, { status: 503 });
  }
}
