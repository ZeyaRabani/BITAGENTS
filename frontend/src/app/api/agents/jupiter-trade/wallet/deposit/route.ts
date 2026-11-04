import { NextResponse } from "next/server";
import { getAuthToken, proxyJupiterTradeDepositVerify } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: { signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  if (!body.signature?.trim()) {
    return NextResponse.json({ error: "signature is required" }, { status: 400 });
  }
  try {
    const res = await proxyJupiterTradeDepositVerify(
      { signature: body.signature.trim() },
      authToken
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agent API" }, { status: 503 });
  }
}
