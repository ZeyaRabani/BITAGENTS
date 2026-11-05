import { NextResponse } from "next/server";
import { getAuthToken, proxyAomiTestSend } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: { destination?: string; amount_sol?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (!body.destination?.trim()) {
    return NextResponse.json({ error: "destination is required" }, { status: 400 });
  }
  try {
    const res = await proxyAomiTestSend(
      { destination: body.destination.trim(), amount_sol: Number(body.amount_sol) || 0 },
      authToken
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
