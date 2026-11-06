import { NextResponse } from "next/server";
import { proxyVolumeHealth } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyVolumeHealth();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        status: "offline",
        detail:
          "Volume agent API is not running. Start it with: cd agent/new && python agents_api.py",
      },
      { status: 503 }
    );
  }
}
