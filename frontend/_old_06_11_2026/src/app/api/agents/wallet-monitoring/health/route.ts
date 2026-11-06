import { NextResponse } from "next/server";
import { proxyResearchAgentHealth } from "@/server/agentsApiProxy";

const SLUG = "wallet-monitoring";

export async function GET() {
  try {
    const res = await proxyResearchAgentHealth(SLUG);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        error: "Cannot reach agent API",
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 503 }
    );
  }
}
