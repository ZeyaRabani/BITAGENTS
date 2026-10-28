import { NextRequest, NextResponse } from "next/server";
import { mapRealAgentToRecord, proxyListLaunchedAgents } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const status = request.nextUrl.searchParams.get("status") === "testing" ? "testing" : "live";
  try {
    const res = await proxyListLaunchedAgents(status);
    const data = await res.json().catch(() => ({ agents: [] }));
    const agents = Array.isArray(data.agents) ? data.agents.map(mapRealAgentToRecord) : [];
    return NextResponse.json({ agents }, { status: res.status });
  } catch {
    return NextResponse.json({ agents: [] }, { status: 503 });
  }
}
