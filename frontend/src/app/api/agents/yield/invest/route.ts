import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyYieldInvest } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  try {
    const body = (await request.json()) as {
      asset?: string;
      capital?: number;
      duration_days?: number;
      yield_type?: string;
    };
    const res = await proxyYieldInvest(
      {
        asset: String(body.asset || "SOL"),
        capital: Number(body.capital),
        duration_days: Number(body.duration_days || 30),
        yield_type: String(body.yield_type || "any"),
      },
      authToken
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Yield agent API offline" }, { status: 503 });
  }
}
