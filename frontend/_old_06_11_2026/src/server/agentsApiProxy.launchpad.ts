// Archived from agentsApiProxy.ts on 06_11_2026. Not part of the live app.

export async function proxyLaunchConfig(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/config`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyLaunchPublicAgents(limit = 100): Promise<Response> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetch(`${getAgentsBaseUrl()}/launch/public?${params}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyLaunchPublicAgent(agentId: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/public/${encodeURIComponent(agentId)}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyLaunchAgentsList(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyLaunchDashboard(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/dashboard`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyLaunchAgent(
  body: {
    name: string;
    description?: string;
    task: string;
    modules: string[];
    signature?: string;
    visibility?: "public" | "private";
    price_per_month_sol?: number | null;
  },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxySubscribeAgent(
  agentId: string,
  body: { signature?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/${encodeURIComponent(agentId)}/subscribe`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyWithdrawCreatorEarnings(
  agentId: string,
  body: { amount_sol?: number; destination_wallet?: string },
  authToken: string
): Promise<Response> {
  return fetch(
    `${getAgentsBaseUrl()}/launch/${encodeURIComponent(agentId)}/withdraw-earnings`,
    {
      method: "POST",
      headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }
  );
}

export async function proxyLaunchAgentGet(agentId: string, authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/${encodeURIComponent(agentId)}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyUpdateLaunchAgent(
  agentId: string,
  body: Record<string, unknown>,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyLaunchAgentChat(
  agentId: string,
  body: Record<string, unknown>,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/launch/${encodeURIComponent(agentId)}/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

// ─── Agent launchpad (custom agents) ──────────────────────────────────────

export async function proxyAgentBuilderChat(
  body: { message: string; session_id?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/builder/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyListLaunchedAgents(status: "live" | "testing" = "live"): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom?status=${status}`, {
    cache: "no-store",
  });
}

export async function proxyMyLaunchedAgents(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/mine`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyGetLaunchedAgent(agentId: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}`, {
    cache: "no-store",
  });
}

export async function proxyUpdateLaunchedAgent(
  agentId: string,
  body: Record<string, unknown>,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}`, {
    method: "PATCH",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDeleteLaunchedAgent(
  agentId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}`, {
    method: "DELETE",
    headers: buildHeaders(authToken),
  });
}

export async function proxyGetLaunchedAgentPriceWatch(
  agentId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}/price-watch`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyGetAgentDraftState(agentId: string, authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}/draft`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyGetAgentBuilderHistory(agentId: string, authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}/builder-history`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyCustomAgentChat(
  agentId: string,
  body: { message: string; session_id?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/agents/custom/${agentId}/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

