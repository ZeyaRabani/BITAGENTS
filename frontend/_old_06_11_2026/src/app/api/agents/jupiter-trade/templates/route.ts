import { NextRequest, NextResponse } from "next/server";
import { proxyJupiterTradeTemplates } from "@/server/agentsApiProxy";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const res = await proxyJupiterTradeTemplates({
      family: searchParams.get("family") || undefined,
      query: searchParams.get("query") || undefined,
      limit: searchParams.get("limit")
        ? Number(searchParams.get("limit"))
        : undefined,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { error: "Templates unavailable", count: 0, templates: [], families: [] },
      { status: 503 }
    );
  }
}
