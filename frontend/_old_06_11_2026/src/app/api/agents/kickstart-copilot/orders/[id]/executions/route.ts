import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyKickstartOrderExecutions } from "@/server/agentsApiProxy";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const { id } = await params;
  const limit = Number(request.nextUrl.searchParams.get("limit") ?? "50");

  try {
    const res = await proxyKickstartOrderExecutions(id, authToken, Number.isFinite(limit) ? limit : 50);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
