import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperConfirmStrategy } from "@/server/agentsApiProxy";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const { id } = await context.params;
  const body = await request.json().catch(() => ({}));
  const res = await proxyHedgeFundPaperConfirmStrategy(id, authToken, body);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
