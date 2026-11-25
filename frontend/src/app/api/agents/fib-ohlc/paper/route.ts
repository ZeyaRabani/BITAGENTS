import { NextResponse } from "next/server";
import { getAuthToken, proxyFibOhlc } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  try {
    const res = await proxyFibOhlc("/paper", { method: "POST", body, authToken });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Cannot reach agent API" },
      { status: 503 }
    );
  }
}
