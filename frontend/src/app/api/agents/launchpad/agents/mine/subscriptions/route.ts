import { NextResponse } from "next/server";
import { getAgentsBaseUrl, buildHeaders, getAuthToken } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await fetch(`${getAgentsBaseUrl()}/agents/mine/subscriptions`, {
      cache: "no-store",
      headers: buildHeaders(authToken),
    });
    const data = await res.json().catch(() => ({ subscriptions: [] }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ subscriptions: [] }, { status: 503 });
  }
}
