import { NextRequest, NextResponse } from "next/server";
import { getAuthToken, proxyYieldInvest } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Missing session token" }, { status: 401 });
  }
  try {
    const body = (await request.json()) as {
      asset?: string;
      capital?: number;
      duration_days?: number;
      yield_type?: string;
      skip_deposit_ledger?: boolean;
      force_protocol?: string;
    };
    const res = await proxyYieldInvest(
      {
        asset: String(body.asset || "SOL"),
        capital: Number(body.capital),
        duration_days: Number(body.duration_days || 30),
        yield_type: String(body.yield_type || "any"),
        skip_deposit_ledger: Boolean(body.skip_deposit_ledger),
        force_protocol: body.force_protocol ? String(body.force_protocol) : undefined,
      },
      authToken
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Yield agent API offline" }, { status: 503 });
  }
}
