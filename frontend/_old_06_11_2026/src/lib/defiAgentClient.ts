import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";
import type { DefiAgentSlug } from "@/lib/defiAgentsConfig";

export type DefiAgentChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type DefiAgentHealth = {
  status: string;
  agent: string;
  model: string;
  pricing?: string;
  auth_required: boolean;
};

export async function fetchDefiAgentHealth(slug: DefiAgentSlug): Promise<DefiAgentHealth | null> {
  try {
    const res = await fetch(`/api/agents/defi/${slug}/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as DefiAgentHealth;
  } catch {
    return null;
  }
}

export async function sendDefiAgentMessage(
  slug: DefiAgentSlug,
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<DefiAgentChatResponse> {
  const res = await fetch(`/api/agents/defi/${slug}/chat`, {
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

  return data as DefiAgentChatResponse;
}

export function mapDefiAgentActions(actions: DefiAgentChatResponse["actions"]): AgentAction[] {
  return mapApiActions(actions);
}
