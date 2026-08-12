import { NextRequest, NextResponse } from "next/server";
import { proxyMultiWalletDcaWithdraw } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const auth = request.headers.get("authorization");
  const token = auth?.startsWith("Bearer ") ? auth.slice("Bearer ".length) : null;
  if (!token) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }
  try {
    const body = await request.json();
    const res = await proxyMultiWalletDcaWithdraw(body, token);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
