import { NextResponse } from "next/server";
import { getAuthToken, proxyMyLaunchedAgents } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyMyLaunchedAgents(authToken);
    const data = await res.json().catch(() => ({ agents: [] }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ agents: [] }, { status: 503 });
  }
}
