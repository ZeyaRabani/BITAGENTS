import { NextResponse } from "next/server";
import { getAuthToken, proxySaveCustomInstructions } from "@/server/agentsApiProxy";

export async function POST(request: Request) {
  const authToken = getAuthToken(request);
  if (!authToken) {
    return NextResponse.json({ error: "Wallet sign-in required" }, { status: 401 });
  }

  try {
    const body = (await request.json()) as {
      agent_type?: string;
      instructions?: string;
    };
    if (!body.agent_type?.trim()) {
      return NextResponse.json({ error: "agent_type is required" }, { status: 400 });
    }

    const res = await proxySaveCustomInstructions(
      {
        agent_type: body.agent_type.trim(),
        instructions: body.instructions ?? "",
      },
      authToken
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Agents API offline" }, { status: 503 });
  }
}
