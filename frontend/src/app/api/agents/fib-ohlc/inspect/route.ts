import { NextResponse } from "next/server";
import { getAuthToken, proxyFibOhlc } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const asset = searchParams.get("asset") || "BTC";
  const lookback = searchParams.get("lookback_days") || "120";
  try {
    const res = await proxyFibOhlc(
      `/inspect?asset=${encodeURIComponent(asset)}&lookback_days=${encodeURIComponent(lookback)}`,
      { authToken }
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Cannot reach agent API" },
      { status: 503 }
    );
  }
}
