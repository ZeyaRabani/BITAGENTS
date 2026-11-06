import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyVolumeCampaigns, proxyVolumeCreateCampaign } from "@/server/agentsApiProxy";

export async function GET(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const activeOnly = request.nextUrl.searchParams.get("active_only") === "true";
  const status = request.nextUrl.searchParams.get("status") ?? undefined;
  const res = await proxyVolumeCampaigns(authToken, { active_only: activeOnly, status });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const body = await request.json();
  const res = await proxyVolumeCreateCampaign(body, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
