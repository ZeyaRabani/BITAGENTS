import { NextResponse } from "next/server";
import { getAuthToken, proxyKickstartDepositVerify } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  let body: { signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const signature = body.signature?.trim();
  if (!signature) {
    return NextResponse.json({ error: "signature is required" }, { status: 400 });
  }
  try {
    const res = await proxyKickstartDepositVerify({ signature }, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
