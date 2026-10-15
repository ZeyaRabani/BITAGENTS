import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyYieldPositionUnwind } from "@/server/agentsApiProxy";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> | { id: string } }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const params = await Promise.resolve(context.params);
  const positionId = String(params.id || "").trim();
  if (!positionId) {
    return NextResponse.json({ error: "Missing position id" }, { status: 400 });
  }
  try {
    const res = await proxyYieldPositionUnwind(positionId, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Yield agent API offline" }, { status: 503 });
  }
}
