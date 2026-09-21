import { NextResponse } from "next/server";
import { proxyLaunchPublicAgent } from "@/server/agentsApiProxy";

export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  const id = params.id?.trim();
  if (!id) {
    return NextResponse.json({ error: "Agent id is required" }, { status: 400 });
  }

  try {
    const res = await proxyLaunchPublicAgent(id);
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data.detail === "string" ? data.detail : data.error ?? "Agent not found";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
