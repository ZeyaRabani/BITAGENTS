import { NextResponse } from "next/server";
import { getAuthToken, proxyLaunchDashboard } from "@/server/agentsApiProxy";

export async function GET(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  try {
    const res = await proxyLaunchDashboard(authToken);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof (data as { detail?: unknown }).detail === "string"
          ? (data as { detail: string }).detail
          : typeof (data as { error?: unknown }).error === "string"
            ? (data as { error: string }).error
            : "Failed to load dashboard";
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Agents API offline";
    return NextResponse.json({ error: message }, { status: 503 });
  }
}
