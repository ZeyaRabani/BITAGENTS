import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyVolumeCampaignStatus } from "@/server/agentsApiProxy";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const { id } = await context.params;
  const body = await request.json();
  const res = await proxyVolumeCampaignStatus(id, body.action, authToken);
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
