import { NextResponse } from "next/server";
import { isMarketAgentSlug, proxyMarketAgentHealth } from "@/server/agentsApiProxy";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  if (!isMarketAgentSlug(slug)) {
    return NextResponse.json({ error: "Unknown agent" }, { status: 404 });
  }
  try {
    const res = await proxyMarketAgentHealth(slug);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { status: "offline", detail: "Agent API is not running. Start it with: cd agent/new && python agents_api.py" },
      { status: 503 }
    );
  }
}
