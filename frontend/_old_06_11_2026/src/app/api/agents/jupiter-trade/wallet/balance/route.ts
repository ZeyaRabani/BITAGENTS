import { NextResponse } from "next/server";
import { getAuthToken, proxyJupiterTradeWalletBalance } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyJupiterTradeWalletBalance(authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
