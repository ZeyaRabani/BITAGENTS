import { NextResponse } from "next/server";
import { proxyKickstartWalletAgent } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyKickstartWalletAgent();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
