import { NextResponse } from "next/server";
import { proxyKickstartHealth } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyKickstartHealth();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        error: "Cannot reach Kickstart Copilot API",
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 503 }
    );
  }
}
