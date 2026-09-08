export type BuilderChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; result: string }[];
};

export async function sendBuilderMessage(
  message: string,
  authToken: string,
  sessionId?: string
): Promise<BuilderChatResponse> {
  const res = await fetch("/api/agents/launchpad/builder/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }
  return data as BuilderChatResponse;
}

export type LaunchedAgentRecord = {
  id: string;
  creator_wallet: string;
  name: string | null;
  handle: string | null;
  category: string | null;
  description: string | null;
  system_prompt: string | null;
  model_tier: string;
  tool_scope: string;
  creator_fee_share_pct: number;
  status: "draft" | "testing" | "live";
  runs: number;
  volume_usd: number;
  created_at: string;
};

export async function fetchLaunchedAgents(status: "live" | "testing" = "live"): Promise<LaunchedAgentRecord[]> {
  const res = await fetch(`/api/agents/launchpad/agents?status=${status}`, { cache: "no-store" });
  const data = await res.json().catch(() => ({ agents: [] }));
  return (data.agents ?? []) as LaunchedAgentRecord[];
}
