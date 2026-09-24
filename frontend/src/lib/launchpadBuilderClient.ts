export type BuilderChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; result: string }[];
  agent_id?: string;
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

export type AgentChecklist = {
  fields_complete: boolean;
  missing_fields: string[];
  notification_set: boolean;
  notification_verified: boolean;
  watch_configured: boolean;
  watch_type: "btc_price" | "product_price" | "news_digest" | null;
  launched: boolean;
};

export type AgentDraftState = {
  agent: Record<string, unknown>;
  watch: Record<string, unknown> | null;
  checklist: AgentChecklist;
};

export async function fetchAgentDraftState(
  agentId: string,
  authToken: string
): Promise<AgentDraftState | null> {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/draft`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) return null;
  return (await res.json()) as AgentDraftState;
}

export async function fetchAgentBuilderHistory(
  agentId: string,
  authToken: string
): Promise<{ session_id: string | null; messages: { role: string; content: string }[] }> {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/builder-history`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) return { session_id: null, messages: [] };
  return await res.json();
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
  notify_channel: "email" | "telegram" | null;
  notify_destination: string | null;
  notify_verified_at: string | null;
};

export async function fetchLaunchedAgents(status: "live" | "testing" = "live"): Promise<LaunchedAgentRecord[]> {
  const res = await fetch(`/api/agents/launchpad/agents?status=${status}`, { cache: "no-store" });
  const data = await res.json().catch(() => ({ agents: [] }));
  return (data.agents ?? []) as LaunchedAgentRecord[];
}

export async function fetchMyLaunchedAgents(authToken: string): Promise<LaunchedAgentRecord[]> {
  const res = await fetch("/api/agents/launchpad/agents/mine", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  const data = await res.json().catch(() => ({ agents: [] }));
  if (!res.ok) return [];
  return (data.agents ?? []) as LaunchedAgentRecord[];
}

/** Every launched agent -- live or still in its testing window -- from any
 * creator, plus (if signed in) the viewer's own non-draft agents in case
 * either public list missed one. Launched agents show up immediately, the
 * same way a token shows up the moment it's launched: no 24h promotion gate
 * hides it from the feed. De-duplicated by id. */
export async function fetchVisibleCustomAgents(authToken?: string): Promise<LaunchedAgentRecord[]> {
  const [live, testing, mine] = await Promise.all([
    fetchLaunchedAgents("live"),
    fetchLaunchedAgents("testing"),
    authToken ? fetchMyLaunchedAgents(authToken) : Promise.resolve([]),
  ]);
  const byId = new Map<string, LaunchedAgentRecord>();
  for (const agent of [...live, ...testing, ...mine]) {
    if (agent.status === "draft") continue;
    byId.set(agent.id, agent);
  }
  return Array.from(byId.values());
}

export async function deleteLaunchedAgent(agentId: string, authToken: string): Promise<boolean> {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return res.ok;
}

export type PriceWatch = {
  id: string;
  threshold_pct: number;
  window_hours: number;
  baseline_price_usd: number | null;
  last_checked_at: string | null;
};

export async function fetchAgentPriceWatch(
  agentId: string,
  authToken: string
): Promise<PriceWatch | null> {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/price-watch`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!res.ok) return null;
  return (await res.json()) as PriceWatch;
}

async function postNotify(agentId: string, path: string, authToken: string, body?: unknown) {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/notify/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${authToken}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { ok: res.ok, data: await res.json().catch(() => ({})) };
}

export function setAgentNotifyEmail(agentId: string, email: string, authToken: string) {
  return postNotify(agentId, "set-email", authToken, { email });
}

export function startAgentNotifyTelegram(agentId: string, authToken: string) {
  return postNotify(agentId, "telegram/start", authToken);
}

export async function getAgentNotifyTelegramStatus(agentId: string, authToken: string) {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}/notify/telegram/status`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return (await res.json()) as { linked: boolean };
}

export function testAgentNotify(agentId: string, authToken: string) {
  return postNotify(agentId, "test", authToken);
}

export function confirmAgentNotify(agentId: string, authToken: string) {
  return postNotify(agentId, "confirm", authToken);
}

export async function updateLaunchedAgent(
  agentId: string,
  updates: { description?: string; threshold_pct?: number },
  authToken: string
): Promise<LaunchedAgentRecord> {
  const res = await fetch(`/api/agents/launchpad/agents/${agentId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(updates),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? data.error ?? "Update failed");
  return data as LaunchedAgentRecord;
}
