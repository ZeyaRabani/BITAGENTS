import { NextResponse } from "next/server";
import { proxyHedgeFundFees } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyHedgeFundFees();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
