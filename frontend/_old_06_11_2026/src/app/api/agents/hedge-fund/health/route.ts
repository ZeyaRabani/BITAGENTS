import { NextResponse } from "next/server";
import { proxyResearchAgentHealth } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyResearchAgentHealth("hedge-fund");
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
