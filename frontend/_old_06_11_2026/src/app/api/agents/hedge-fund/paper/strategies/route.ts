import { NextRequest, NextResponse } from "next/server";
import {
  getAuthToken,
  proxyHedgeFundPaperCreateStrategy,
  proxyHedgeFundPaperStrategies,
} from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const res = await proxyHedgeFundPaperStrategies(authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const body = await request.json();
  const res = await proxyHedgeFundPaperCreateStrategy(body, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
