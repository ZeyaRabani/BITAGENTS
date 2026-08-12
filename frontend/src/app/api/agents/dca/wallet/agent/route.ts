import { NextRequest, NextResponse } from "next/server";
import { proxyDcaWalletAgent } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get("authorization");
    const authToken = authHeader?.startsWith("Bearer ") ? authHeader.slice("Bearer ".length).trim() : undefined;
    const res = await proxyDcaWalletAgent(authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "DCA agent API offline" }, { status: 503 });
  }
}
