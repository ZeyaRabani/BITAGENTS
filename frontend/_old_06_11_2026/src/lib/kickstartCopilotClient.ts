import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";

export type KickstartChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type KickstartHealth = {
  status: string;
  agent: string;
  model: string;
  pricing: string;
  auth_required: boolean;
};

export async function fetchKickstartHealth(): Promise<KickstartHealth | null> {
  try {
    const res = await fetch("/api/agents/kickstart-copilot/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as KickstartHealth;
  } catch {
    return null;
  }
}

export async function sendKickstartMessage(
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<KickstartChatResponse> {
  const res = await fetch("/api/agents/kickstart-copilot/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId, history }),
  });

  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }

  return data as KickstartChatResponse;
}

export function mapKickstartActions(
  actions: KickstartChatResponse["actions"]
): AgentAction[] {
  return mapApiActions(actions);
}
