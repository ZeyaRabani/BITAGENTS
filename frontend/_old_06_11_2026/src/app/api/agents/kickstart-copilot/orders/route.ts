import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyKickstartOrders } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const activeOnly = request.nextUrl.searchParams.get("active_only") === "true";
  const refreshMetrics = request.nextUrl.searchParams.get("refresh_metrics") === "true";

  try {
    const res = await proxyKickstartOrders(authToken, {
      active_only: activeOnly,
      refresh_metrics: refreshMetrics,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
