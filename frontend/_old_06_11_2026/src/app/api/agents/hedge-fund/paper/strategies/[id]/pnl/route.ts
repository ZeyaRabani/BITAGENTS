import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperStrategyPnl } from "@/server/agentsApiProxy";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const { id } = await context.params;
  const res = await proxyHedgeFundPaperStrategyPnl(id, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
