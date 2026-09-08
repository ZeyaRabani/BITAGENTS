import { NextResponse } from "next/server";
import { proxyGetLaunchedAgent } from "@/server/agentsApiProxy";

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
