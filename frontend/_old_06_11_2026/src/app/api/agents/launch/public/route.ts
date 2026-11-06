import { NextResponse } from "next/server";
import { proxyLaunchPublicAgents } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const limitRaw = searchParams.get("limit");
  const limit = limitRaw ? Number(limitRaw) : 100;

  try {
    const res = await proxyLaunchPublicAgents(
      Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 200) : 100
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
