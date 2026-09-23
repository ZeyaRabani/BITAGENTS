import { NextResponse } from "next/server";
import { getAuthToken, proxyGetLaunchedAgent, proxyUpdateLaunchedAgent } from "@/server/agentsApiProxy";

export async function GET(_request: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  try {
    const res = await proxyGetLaunchedAgent(agentId);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}

export async function PATCH(request: Request, { params }: { params: Promise<{ agentId: string }> }) {
  const { agentId } = await params;
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const body = await request.json();
    const res = await proxyUpdateLaunchedAgent(agentId, body, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}
