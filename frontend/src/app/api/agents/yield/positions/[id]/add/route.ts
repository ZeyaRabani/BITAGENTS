import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyYieldPositionAdd } from "@/server/agentsApiProxy";

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
    const body = (await request.json()) as { capital?: number };
    const res = await proxyYieldPositionAdd(
      positionId,
      { capital: Number(body.capital) },
      authToken
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Yield agent API offline" }, { status: 503 });
  }
}
