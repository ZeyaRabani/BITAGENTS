import { NextResponse } from "next/server";
import { proxyAgentsHealth } from "@/server/agentsApiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Lightweight wake/keep-alive for the Render agents API.
 * Browser pages call this so cold starts begin as soon as the app is open.
 */
export async function GET() {
  try {
    const res = await proxyAgentsHealth(false);
    const ok = res.ok;
    return NextResponse.json(
      {
        ok,
        upstream_status: res.status,
        warmed: ok,
      },
      { status: ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json(
      { ok: false, warmed: false, detail: "Agents API unreachable" },
      { status: 503 }
    );
  }
}
