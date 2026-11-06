import { NextResponse } from "next/server";
import { getAgentsBaseUrl, buildHeaders, getAuthToken } from "@/server/agentsApiProxy";

async function forward(request: Request, agentId: string, path: string[]) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  const url = `${getAgentsBaseUrl()}/agents/custom/${agentId}/notify/${path.join("/")}`;
  const init: RequestInit = {
    method: request.method,
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    cache: "no-store",
  };
  if (request.method !== "GET") {
    const bodyText = await request.text();
    if (bodyText) init.body = bodyText;
  }
  try {
    const res = await fetch(url, init);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}

export async function GET(request: Request, { params }: { params: Promise<{ agentId: string; path: string[] }> }) {
  const { agentId, path } = await params;
  return forward(request, agentId, path);
}

export async function POST(request: Request, { params }: { params: Promise<{ agentId: string; path: string[] }> }) {
  const { agentId, path } = await params;
  return forward(request, agentId, path);
}
