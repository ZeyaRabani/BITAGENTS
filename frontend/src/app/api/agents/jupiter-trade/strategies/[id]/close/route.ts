import { NextResponse } from "next/server";
import { getAuthToken, proxyJupiterTradeCloseStrategy } from "@/server/agentsApiProxy";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  const { id } = await context.params;
  try {
    const res = await proxyJupiterTradeCloseStrategy(id, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
