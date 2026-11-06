import { NextResponse } from "next/server";
import { proxyResearchAgentHealth } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyResearchAgentHealth("jupiter-trade");
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        status: "degraded",
        agent: "Jupiter Trade Agent",
        model: "hosted LLM",
        auth_required: true,
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 200 }
    );
  }
}
