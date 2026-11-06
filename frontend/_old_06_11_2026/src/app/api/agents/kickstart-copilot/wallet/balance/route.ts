import { NextResponse } from "next/server";
import { getAuthToken, proxyKickstartWalletBalance } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  try {
    const res = await proxyKickstartWalletBalance(authToken);
    const data = await res.json();
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Failed to load balance";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
