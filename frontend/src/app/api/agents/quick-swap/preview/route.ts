import { NextResponse } from "next/server";
import { getAuthToken, proxyQuickSwapPreview } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: { message?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const message = body.message?.trim();
  if (!message) {
    return NextResponse.json({ error: "message is required" }, { status: 400 });
  }

  try {
    const res = await proxyQuickSwapPreview({ message }, authToken);
    const text = await res.text();
    let data: Record<string, unknown>;
    try {
      data = text.trim() ? (JSON.parse(text) as Record<string, unknown>) : {};
    } catch {
      return NextResponse.json(
        { error: "Agent API returned non-JSON", detail: text.trim().slice(0, 240) || `HTTP ${res.status}` },
        { status: 502 }
      );
    }
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach agent API";
    return NextResponse.json({ error: "Cannot reach agent API", detail }, { status: 503 });
  }
}
