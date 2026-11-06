import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperDismissStrategy } from "@/server/agentsApiProxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const { id } = await params;
  const res = await proxyHedgeFundPaperDismissStrategy(id, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
