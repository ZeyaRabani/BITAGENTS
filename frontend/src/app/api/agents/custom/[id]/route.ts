import { NextResponse } from "next/server";
import {
  getAuthToken,
  proxyDeleteCustomAgent,
  proxyGetCustomAgent,
} from "@/server/agentsApiProxy";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const { id } = await params;
  try {
    const res = await proxyGetCustomAgent(id, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}

export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  const { id } = await params;
  try {
    const res = await proxyDeleteCustomAgent(id, authToken);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Cannot reach agents API" }, { status: 503 });
  }
}
