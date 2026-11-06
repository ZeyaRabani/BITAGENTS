import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyVolumePoolEnsure } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  const body = await request.json();
  const res = await proxyVolumePoolEnsure(
    {
      base_token: String(body.base_token ?? "").trim(),
      quote_token: String(body.quote_token ?? "SOL").trim(),
      create_if_missing: Boolean(body.create_if_missing),
    },
    authToken
  );
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
