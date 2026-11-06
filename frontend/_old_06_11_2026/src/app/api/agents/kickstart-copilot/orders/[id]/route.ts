import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyKickstartUpdateOrder } from "@/server/agentsApiProxy";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const { id } = await params;
  let body: { amount_sol?: number; limit_price_usd?: number; slippage_bps?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const res = await proxyKickstartUpdateOrder(id, body, authToken);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
