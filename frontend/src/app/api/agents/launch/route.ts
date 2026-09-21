import { NextResponse } from "next/server";
import { getAuthToken, proxyLaunchAgent, proxyLaunchAgentsList } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  try {
    const res = await proxyLaunchAgentsList(authToken);
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data.detail === "string" ? data.detail : data.error ?? "Failed to list agents";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  let body: {
    name?: string;
    description?: string;
    task?: string;
    modules?: string[];
    signature?: string;
    visibility?: string;
    price_per_month_sol?: number | null;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const name = body.name?.trim();
  const task = body.task?.trim();
  const signature = body.signature?.trim();
  const modules = Array.isArray(body.modules) ? body.modules : [];
  const visibility = body.visibility === "public" ? "public" : "private";
  const price =
    typeof body.price_per_month_sol === "number" && Number.isFinite(body.price_per_month_sol)
      ? body.price_per_month_sol
      : null;

  if (!name || !task || !signature || modules.length === 0) {
    return NextResponse.json(
      { error: "name, task, modules, and signature are required" },
      { status: 400 }
    );
  }

  if (visibility === "public" && (price === null || price <= 0)) {
    return NextResponse.json(
      { error: "Public agents require a price per month greater than 0 SOL" },
      { status: 400 }
    );
  }

  try {
    const res = await proxyLaunchAgent(
      {
        name,
        description: body.description?.trim() ?? "",
        task,
        modules,
        signature,
        visibility,
        price_per_month_sol: visibility === "public" ? price : null,
      },
      authToken
    );
    const data = await res.json();
    if (!res.ok) {
      const detail =
        typeof data.detail === "string" ? data.detail : data.error ?? "Launch failed";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
