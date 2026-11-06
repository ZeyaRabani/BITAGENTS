import { NextRequest, NextResponse } from "next/server";
import { proxyListLaunchedAgents } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const status = request.nextUrl.searchParams.get("status") === "testing" ? "testing" : "live";
  try {
    const res = await proxyListLaunchedAgents(status);
    const data = await res.json().catch(() => ({ agents: [] }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ agents: [] }, { status: 503 });
  }
}
