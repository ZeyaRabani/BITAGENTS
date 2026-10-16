import { NextResponse } from "next/server";
import { getAuthToken, proxyWithdrawCreatorEarnings } from "@/server/agentsApiProxy";

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

  let body: { amount_sol?: number; destination_wallet?: string } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  try {
    const res = await proxyWithdrawCreatorEarnings(agentId, body, authToken);
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data.detail === "string" ? data.detail : data.error ?? "Withdraw failed";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
