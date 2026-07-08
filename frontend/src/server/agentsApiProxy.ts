const AGENTS_API_URL =
  process.env.AGENTS_API_URL ?? process.env.DCA_AGENT_URL ?? "http://127.0.0.1:8765";
const AGENTS_INTERNAL_API_KEY =
  process.env.AGENTS_INTERNAL_API_KEY ?? process.env.DCA_INTERNAL_API_KEY ?? "";

function getAgentsBaseUrl() {
  return AGENTS_API_URL.replace(/\/$/, "");
}

function buildHeaders(authToken?: string, extra?: Record<string, string>): HeadersInit {
  const headers: Record<string, string> = { ...extra };
  if (AGENTS_INTERNAL_API_KEY) {
    headers["X-Internal-Key"] = AGENTS_INTERNAL_API_KEY;
  }
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  return headers;
}

function getAuthToken(request?: Request): string | undefined {
  if (!request) return undefined;
  const header = request.headers.get("authorization");
  if (!header?.startsWith("Bearer ")) return undefined;
  return header.slice("Bearer ".length).trim();
}

export async function proxyAgentsHealth(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/health`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyKickstartHealth(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/health`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyAgentsAuthChallenge(userWallet: string): Promise<Response> {
  const params = new URLSearchParams({ user_wallet: userWallet });
  return fetch(`${getAgentsBaseUrl()}/auth/challenge?${params}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyAgentsAuthVerify(body: {
  user_wallet: string;
  message: string;
  signature: string;
}): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/auth/verify`, {
    method: "POST",
    headers: buildHeaders(undefined, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyAgentsAuthMe(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/auth/me`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyKickstartChat(
  body: {
    message: string;
    session_id?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyKickstartWalletAgent(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/wallet/agent`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyKickstartWalletBalance(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/wallet/balance`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyKickstartDepositVerify(
  body: { signature: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/wallet/deposit/verify`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyKickstartWithdraw(
  body: { token: string; amount: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/wallet/withdraw`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDcaHealth(): Promise<Response> {
  return proxyAgentsHealth();
}

export async function proxyDcaAuthChallenge(userWallet: string): Promise<Response> {
  return proxyAgentsAuthChallenge(userWallet);
}

export async function proxyDcaAuthVerify(body: {
  user_wallet: string;
  message: string;
  signature: string;
}): Promise<Response> {
  return proxyAgentsAuthVerify(body);
}

export async function proxyDcaAuthMe(authToken: string): Promise<Response> {
  return proxyAgentsAuthMe(authToken);
}

export async function proxyDcaChat(
  body: { message: string; session_id?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDcaWalletAgent(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/wallet/agent`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyDcaResolveToken(query: string): Promise<Response> {
  const params = new URLSearchParams({ query });
  return fetch(`${getAgentsBaseUrl()}/tokens/resolve?${params}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyDcaWalletBalance(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/wallet/balance`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDcaDepositVerify(
  body: { signature: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/wallet/deposit/verify`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDcaWithdraw(
  body: { token: string; amount: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/wallet/withdraw`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDcaPlans(
  authToken: string,
  params?: { active_only?: boolean; status?: string }
): Promise<Response> {
  const search = new URLSearchParams();
  if (params?.active_only) search.set("active_only", "true");
  if (params?.status) search.set("status", params.status);
  const qs = search.toString();
  return fetch(`${getAgentsBaseUrl()}/plans${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDcaPlanExecutions(
  planId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/plans/${encodeURIComponent(planId)}/executions`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDcaPlanStatus(
  planId: string,
  action: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/plans/${encodeURIComponent(planId)}/status`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify({ action }),
  });
}

export async function proxyDcaWalletLedger(
  authToken: string,
  limit = 50
): Promise<Response> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetch(`${getAgentsBaseUrl()}/wallet/ledger?${params}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDcaExecutions(
  authToken: string,
  limit = 100
): Promise<Response> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetch(`${getAgentsBaseUrl()}/wallet/dca-executions?${params}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDcaMetrics(refresh = false): Promise<Response> {
  const params = refresh ? "?refresh=true" : "";
  return fetch(`${getAgentsBaseUrl()}/metrics${params}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyListCustomAgents(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/custom/agents`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyCreateCustomAgent(
  body: { name: string; description?: string; system_prompt: string; model?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/custom/agents`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyGetCustomAgent(
  agentId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/custom/agents/${encodeURIComponent(agentId)}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyDeleteCustomAgent(
  agentId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/custom/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
    headers: buildHeaders(authToken),
  });
}

export async function proxyCustomAgentChat(
  agentId: string,
  body: { message: string; history?: { role: "user" | "assistant"; content: string }[] },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/custom/agents/${encodeURIComponent(agentId)}/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export { getAuthToken, getAgentsBaseUrl, buildHeaders };
