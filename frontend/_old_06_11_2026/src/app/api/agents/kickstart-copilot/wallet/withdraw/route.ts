import { NextResponse } from "next/server";
import { getAuthToken, proxyKickstartWithdraw } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: { token?: string; amount?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const token = body.token?.trim();
  const amount = body.amount;
  if (!token || typeof amount !== "number" || amount <= 0) {
    return NextResponse.json({ error: "token and positive amount are required" }, { status: 400 });
  }

  try {
    const res = await proxyKickstartWithdraw({ token, amount }, authToken);
    const data = await res.json();
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Withdrawal failed";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "EasyA agent API offline" }, { status: 503 });
  }
}
