import { NextRequest, NextResponse } from "next/server";
import { proxyVolumeAuthVerify } from "@/server/agentsApiProxy";

export async function POST(request: NextRequest) {
  const body = await request.json();
  try {
    const res = await proxyVolumeAuthVerify(body);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Volume agent API offline" }, { status: 503 });
  }
}
