import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyHedgeFundWalletAgent } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  try {
    const res = await proxyHedgeFundWalletAgent(authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Hedge Fund agent API offline" }, { status: 503 });
  }
}
