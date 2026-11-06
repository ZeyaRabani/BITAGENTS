import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperAnalyze } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const body = await request.json().catch(() => ({}));
  const res = await proxyHedgeFundPaperAnalyze(body, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
