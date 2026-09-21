import { NextResponse } from "next/server";
import { proxyLaunchConfig } from "@/server/agentsApiProxy";

export async function GET() {
  try {
    const res = await proxyLaunchConfig();
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
