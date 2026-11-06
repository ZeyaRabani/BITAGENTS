import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperMonitor } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const force = request.nextUrl.searchParams.get("force") === "true";
  const res = await proxyHedgeFundPaperMonitor(authToken, force);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
