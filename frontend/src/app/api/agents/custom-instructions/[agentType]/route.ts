import { NextResponse } from "next/server";
import { getAuthToken, proxyGetCustomInstructions } from "@/server/agentsApiProxy";

export async function GET(
  request: Request,
  { params }: { params: { agentType: string } }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const agentType = params.agentType?.trim();
  if (!agentType) {
    return NextResponse.json({ error: "agent_type is required" }, { status: 400 });
  }

  try {
    const res = await proxyGetCustomInstructions(agentType, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
