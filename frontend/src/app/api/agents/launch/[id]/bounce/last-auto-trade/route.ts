import { NextResponse } from "next/server";
import { getAuthToken, proxyGetBounceLastAutoTrade } from "@/server/agentsApiProxy";

export async function GET(request: Request, { params }: { params: { id: string } }) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyGetBounceLastAutoTrade(params.id, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
