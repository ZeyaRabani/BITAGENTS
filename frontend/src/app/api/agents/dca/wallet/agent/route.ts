import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyDcaWalletAgent } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  try {
    const res = await proxyDcaWalletAgent(authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "DCA agent API offline" }, { status: 503 });
  }
}
