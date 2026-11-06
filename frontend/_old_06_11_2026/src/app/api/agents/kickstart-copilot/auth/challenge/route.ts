import { NextResponse } from "next/server";
import { proxyAgentsAuthChallenge } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userWallet = searchParams.get("user_wallet")?.trim();
  if (!userWallet || userWallet.length < 32) {
    return NextResponse.json({ error: "user_wallet is required" }, { status: 400 });
  }

  try {
    const res = await proxyAgentsAuthChallenge(userWallet);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}
