import { NextResponse } from "next/server";
import { getAuthToken, proxySubscribeAgent } from "@/server/agentsApiProxy";

export async function POST(
  request: Request,
  { params }: { params: { id: string } }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const agentId = params.id?.trim();
  if (!agentId) {
    return NextResponse.json({ error: "Agent id is required" }, { status: 400 });
  }

  let body: { signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const signature = body.signature?.trim();
  if (!signature) {
    return NextResponse.json({ error: "signature is required" }, { status: 400 });
  }

  try {
    const res = await proxySubscribeAgent(agentId, { signature }, authToken);
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data.detail === "string" ? data.detail : data.error ?? "Subscribe failed";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
