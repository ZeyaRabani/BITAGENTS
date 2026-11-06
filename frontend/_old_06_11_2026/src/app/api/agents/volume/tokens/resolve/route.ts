import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyVolumeResolveToken } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("query")?.trim();
  if (!query) {
    return NextResponse.json({ error: "query is required" }, { status: 400 });
  }
  const res = await proxyVolumeResolveToken(query);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
