import { NextResponse } from "next/server";
import { proxyAgentsAuthVerify } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  let body: { user_wallet?: string; message?: string; signature?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!body.user_wallet || !body.message || !body.signature) {
    return NextResponse.json({ error: "user_wallet, message, and signature are required" }, { status: 400 });
  }

  try {
    const res = await proxyAgentsAuthVerify({
      user_wallet: body.user_wallet,
      message: body.message,
      signature: body.signature,
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}
