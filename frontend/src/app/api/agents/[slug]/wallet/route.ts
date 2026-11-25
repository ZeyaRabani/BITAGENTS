import { NextResponse } from "next/server";
import { getAuthToken, isMarketAgentSlug, proxyMarketAgentWallet } from "@/server/agentsApiProxy";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  if (!isMarketAgentSlug(slug)) {
    return NextResponse.json({ error: "Unknown agent" }, { status: 404 });
  }
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  try {
    const res = await proxyMarketAgentWallet(slug, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agent API offline" }, { status: 503 });
  }
}
