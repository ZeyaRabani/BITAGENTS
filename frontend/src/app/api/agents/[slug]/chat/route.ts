import { NextResponse } from "next/server";
import { getAuthToken, isMarketAgentSlug, proxyMarketAgentChat } from "@/server/agentsApiProxy";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  if (!isMarketAgentSlug(slug)) {
    return NextResponse.json({ error: "Unknown agent" }, { status: 404 });
  }
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: { message?: string; session_id?: string };
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
    const res = await proxyMarketAgentChat(
      slug,
      { message, session_id: body.session_id },
      authToken
    );
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
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Cannot reach the agent API";
    return NextResponse.json(
      {
        error: "Cannot reach the agent API",
        detail: `${detail}. Start the agent locally: cd agent/new && python agents_api.py`,
      },
      { status: 503 }
    );
  }
}
