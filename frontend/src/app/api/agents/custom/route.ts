import { NextResponse } from "next/server";
import {
  getAuthToken,
  proxyCreateCustomAgent,
  proxyListCustomAgents,
} from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  try {
    const res = await proxyListCustomAgents(authToken);
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

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: { name?: string; description?: string; system_prompt?: string; model?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const name = body.name?.trim();
  const systemPrompt = body.system_prompt?.trim();
  if (!name || !systemPrompt) {
    return NextResponse.json(
      { error: "name and system_prompt are required" },
      { status: 400 }
    );
  }

  try {
    const res = await proxyCreateCustomAgent(
      { name, description: body.description, system_prompt: systemPrompt, model: body.model },
      authToken
    );
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
