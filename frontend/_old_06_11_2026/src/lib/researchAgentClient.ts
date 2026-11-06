import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";
import type { ResearchAgentSlug } from "@/lib/researchAgentsConfig";

export type ResearchAgentChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type ResearchAgentHealth = {
  status: string;
  agent: string;
  model: string;
  pricing?: string;
  auth_required: boolean;
};

export async function fetchResearchAgentHealth(
  slug: ResearchAgentSlug
): Promise<ResearchAgentHealth | null> {
  try {
    const res = await fetch(`/api/agents/${slug}/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as ResearchAgentHealth;
  } catch {
    return null;
  }
}

export async function sendResearchAgentMessage(
  slug: ResearchAgentSlug,
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<ResearchAgentChatResponse> {
  const res = await fetch(`/api/agents/${slug}/chat`, {
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

  return data as ResearchAgentChatResponse;
}

export function mapResearchAgentActions(
  actions: ResearchAgentChatResponse["actions"]
): AgentAction[] {
  return mapApiActions(actions);
}
