import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyVolumeAuthMe } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const res = await proxyVolumeAuthMe(authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
