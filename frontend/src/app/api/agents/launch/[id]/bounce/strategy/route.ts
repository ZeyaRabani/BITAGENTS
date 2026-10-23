import { NextResponse } from "next/server";
import { getAuthToken, proxyGetBounceStrategy, proxySetBounceStrategy } from "@/server/agentsApiProxy";

export async function GET(request: Request, { params }: { params: { id: string } }) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const res = await proxyGetBounceStrategy(params.id, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}

export async function POST(request: Request, { params }: { params: { id: string } }) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }
  try {
    const body = await request.json();
    const res = await proxySetBounceStrategy(params.id, body, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
