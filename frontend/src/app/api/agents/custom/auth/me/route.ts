import { NextResponse } from "next/server";
import { getAuthToken, proxyAgentsAuthMe } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }

  try {
    const res = await proxyAgentsAuthMe(authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}
