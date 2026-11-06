import { NextResponse } from "next/server";
import { proxyVolumeWalletAgent } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyVolumeWalletAgent();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Volume agent API offline" }, { status: 503 });
  }
}
