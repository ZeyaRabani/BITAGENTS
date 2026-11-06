import { NextResponse } from "next/server";
import { getAuthToken, proxyResearchAgentChat, proxyResearchAgentHealth } from "@/server/agentsApiProxy";
import { isDefiAgentSlug } from "@/lib/defiAgentsConfig";

export async function handleDefiAgentHealth(slug: string) {
  if (!isDefiAgentSlug(slug)) {
    return NextResponse.json({ error: "Unknown DeFi agent" }, { status: 404 });
  }

  try {
    const res = await proxyResearchAgentHealth(slug);
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        status: "degraded",
        agent: slug,
        model: "hosted LLM",
        auth_required: true,
        pricing: "wallet sign-in required",
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 200 }
    );
  }
}

export async function handleDefiAgentChat(request: Request, slug: string) {
  if (!isDefiAgentSlug(slug)) {
    return NextResponse.json({ error: "Unknown DeFi agent" }, { status: 404 });
  }

  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: {
    message?: string;
    session_id?: string;
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

  try {
    const res = await proxyResearchAgentChat(
      slug,
      { message, session_id: body.session_id, history: body.history },
      authToken
    );
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      {
        error: "Cannot reach agent API",
        detail: "Start the agent API: cd agent/new && python agents_api.py",
      },
      { status: 503 }
    );
  }
}
