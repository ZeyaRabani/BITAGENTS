import { NextResponse } from "next/server";
import { getAuthToken, proxyCustomAgentChat } from "@/server/agentsApiProxy";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: {
    message?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const message = body.message?.trim();
  if (!message) {
    return NextResponse.json({ error: "message is required" }, { status: 400 });
  }

  const { id } = await params;
  try {
    const res = await proxyCustomAgentChat(id, { message, history: body.history }, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      {
        error: "Cannot reach agents API",
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 503 }
    );
  }
}
