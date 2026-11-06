import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundPaperUpdateStrategy } from "@/server/agentsApiProxy";

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const { id } = await context.params;
  const body = await request.json();
  const res = await proxyHedgeFundPaperUpdateStrategy(id, body, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
