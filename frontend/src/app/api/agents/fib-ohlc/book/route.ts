import { NextResponse } from "next/server";
import { getAuthToken, proxyFibOhlc } from "@/server/agentsApiProxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyFibOhlc("/book", { authToken });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Cannot reach agent API" },
      { status: 503 }
    );
  }
}
