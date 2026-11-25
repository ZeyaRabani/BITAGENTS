import { NextResponse } from "next/server";
import { proxyFibOhlc } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const res = await proxyFibOhlc("/health");
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Cannot reach agent API" },
      { status: 503 }
    );
  }
}
