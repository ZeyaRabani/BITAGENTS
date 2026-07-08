export type CustomAgent = {
  id: string;
  owner_wallet: string;
  name: string;
  description: string | null;
  system_prompt: string;
  model: string | null;
  created_at: string;
};

export type CustomAgentChatResponse = {
  reply: string;
};

async function parseJsonOrThrow(res: Response) {
  const data = await res.json();
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }
  return data;
}

export async function listCustomAgents(authToken: string): Promise<CustomAgent[]> {
  const res = await fetch("/api/agents/custom", {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  const data = await parseJsonOrThrow(res);
  return (data.agents ?? []) as CustomAgent[];
}

export async function createCustomAgent(
  input: { name: string; description?: string; system_prompt: string; model?: string },
  authToken: string
): Promise<CustomAgent> {
  const res = await fetch("/api/agents/custom", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(input),
  });
  return (await parseJsonOrThrow(res)) as CustomAgent;
}

export async function getCustomAgent(agentId: string, authToken: string): Promise<CustomAgent> {
  const res = await fetch(`/api/agents/custom/${encodeURIComponent(agentId)}`, {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  return (await parseJsonOrThrow(res)) as CustomAgent;
}

export async function deleteCustomAgent(agentId: string, authToken: string): Promise<void> {
  const res = await fetch(`/api/agents/custom/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  await parseJsonOrThrow(res);
}

export async function sendCustomAgentMessage(
  agentId: string,
  message: string,
  authToken: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<CustomAgentChatResponse> {
  const res = await fetch(`/api/agents/custom/${encodeURIComponent(agentId)}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, history }),
  });
  return (await parseJsonOrThrow(res)) as CustomAgentChatResponse;
}
