export type LaunchedAgent = {
  id: string;
  user_wallet: string;
  name: string;
  description: string;
  task: string;
  modules: string[];
  visibility: "public" | "private";
  price_per_month_sol: number | null;
  fee_sol: number;
  fee_signature: string;
  fee_wallet: string;
  status: string;
  explorer_url?: string | null;
  created_at?: string;
  active_subscribers?: number;
  creator_payout_wallet?: string | null;
  platform_fee_wallet?: string | null;
  platform_fee_rate?: number;
  payment_required?: boolean;
  mode?: "development" | "testing" | "production";
};

export type AgentSubscription = {
  id: string;
  agent_id: string;
  buyer_wallet: string;
  seller_wallet: string;
  price_sol: number;
  payment_signature: string;
  status: string;
  starts_at?: string;
  expires_at?: string;
  explorer_url?: string | null;
  created_at?: string;
  agent_name?: string | null;
  agent_description?: string | null;
  agent_visibility?: string | null;
  agent_price_per_month_sol?: number | null;
  agent_status?: string | null;
  agent_modules?: string[] | null;
};

export type LaunchDashboard = {
  listed_for_sale: LaunchedAgent[];
  private_agents: LaunchedAgent[];
  bought: AgentSubscription[];
  sales: AgentSubscription[];
  counts: {
    listed_for_sale: number;
    private_agents: number;
    bought: number;
    sales: number;
  };
  creator_payout_wallet?: string | null;
  platform_fee_rate?: number;
  mode?: "development" | "testing" | "production";
  payment_required?: boolean;
};

export type LaunchConfig = {
  mode?: "development" | "testing" | "production";
  fee_sol: number;
  fee_wallet: string | null;
  configured: boolean;
  payment_required?: boolean;
  platform_fee_rate?: number;
  cluster?: string;
  allowed_modules: string[];
};

export type LaunchAgentResponse = {
  status: "confirmed" | "already_recorded";
  agent: LaunchedAgent;
  fee_sol?: number;
  paid_sol?: number;
  message?: string;
};

async function readError(res: Response): Promise<string> {
  const data = await res.json().catch(() => null);
  if (data && typeof data === "object") {
    const obj = data as { error?: string; detail?: string };
    if (typeof obj.error === "string") return obj.error;
    if (typeof obj.detail === "string") return obj.detail;
  }
  return res.statusText || "Request failed";
}

export async function fetchLaunchConfig(): Promise<LaunchConfig | null> {
  try {
    const res = await fetch("/api/agents/launch/config", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as LaunchConfig;
  } catch {
    return null;
  }
}

export async function listLaunchedAgents(authToken: string): Promise<LaunchedAgent[]> {
  const res = await fetch("/api/agents/launch", {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  const data = (await res.json()) as { agents?: LaunchedAgent[] };
  return data.agents ?? [];
}

export async function fetchPublicLaunchedAgents(): Promise<LaunchedAgent[]> {
  try {
    const res = await fetch("/api/agents/launch/public", { cache: "no-store" });
    if (!res.ok) return [];
    const data = (await res.json()) as { agents?: LaunchedAgent[] };
    return data.agents ?? [];
  } catch {
    return [];
  }
}

export async function fetchPublicLaunchedAgent(id: string): Promise<LaunchedAgent | null> {
  try {
    const res = await fetch(`/api/agents/launch/public/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { agent?: LaunchedAgent };
    return data.agent ?? null;
  } catch {
    return null;
  }
}

export async function fetchLaunchDashboard(authToken: string): Promise<LaunchDashboard> {
  const res = await fetch("/api/agents/launch/dashboard", {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as LaunchDashboard;
}

export async function subscribeToAgent(
  agentId: string,
  signature: string,
  authToken: string
): Promise<{
  status: string;
  subscription: AgentSubscription;
  agent: LaunchedAgent;
  message?: string;
}> {
  const res = await fetch(`/api/agents/launch/${encodeURIComponent(agentId)}/subscribe`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ signature }),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as {
    status: string;
    subscription: AgentSubscription;
    agent: LaunchedAgent;
    message?: string;
  };
}

export async function fetchLaunchedAgent(
  agentId: string,
  authToken: string
): Promise<{ agent: LaunchedAgent; access?: { allowed: boolean; reason?: string } }> {
  const res = await fetch(`/api/agents/launch/${encodeURIComponent(agentId)}`, {
    headers: { Authorization: `Bearer ${authToken}` },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as { agent: LaunchedAgent; access?: { allowed: boolean; reason?: string } };
}

export async function updateLaunchedAgent(
  agentId: string,
  body: {
    name: string;
    description?: string;
    task: string;
    modules: string[];
    visibility: "public" | "private";
    price_per_month_sol?: number | null;
  },
  authToken: string
): Promise<LaunchAgentResponse> {
  const res = await fetch(`/api/agents/launch/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as LaunchAgentResponse;
}

export async function chatWithLaunchedAgent(
  agentId: string,
  body: {
    message: string;
    session_id?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
  authToken: string
): Promise<{ reply: string; session_id: string; actions?: unknown[] }> {
  const res = await fetch(`/api/agents/launch/${encodeURIComponent(agentId)}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as { reply: string; session_id: string; actions?: unknown[] };
}

export async function launchAgent(
  body: {
    name: string;
    description?: string;
    task: string;
    modules: string[];
    signature?: string;
    visibility: "public" | "private";
    price_per_month_sol?: number | null;
  },
  authToken: string
): Promise<LaunchAgentResponse> {
  const res = await fetch("/api/agents/launch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return (await res.json()) as LaunchAgentResponse;
}
