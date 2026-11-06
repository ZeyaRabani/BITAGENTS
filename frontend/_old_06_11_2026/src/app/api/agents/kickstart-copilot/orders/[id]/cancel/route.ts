import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyKickstartCancelOrder } from "@/server/agentsApiProxy";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const { id } = await params;
  try {
    const res = await proxyKickstartCancelOrder(id, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
