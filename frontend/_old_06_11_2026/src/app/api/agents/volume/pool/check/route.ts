import { NextRequest, NextResponse } from "next/server";
import { proxyVolumePoolCheck } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const baseToken =
    request.nextUrl.searchParams.get("base_token")?.trim() ||
    request.nextUrl.searchParams.get("base_mint")?.trim();
  if (!baseToken) {
    return NextResponse.json({ error: "base_token is required" }, { status: 400 });
  }
  const quoteToken =
    request.nextUrl.searchParams.get("quote_token")?.trim() ||
    request.nextUrl.searchParams.get("quote_mint")?.trim() ||
    "SOL";
  const res = await proxyVolumePoolCheck(baseToken, quoteToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
