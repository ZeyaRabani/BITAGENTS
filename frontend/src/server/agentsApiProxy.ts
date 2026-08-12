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

export async function proxyAgentsHealth(pingLlm = false): Promise<Response> {
  const params = pingLlm ? "?ping_llm=true" : "";
  return fetch(`${getAgentsBaseUrl()}/health${params}`, {
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

export async function proxyResearchAgentHealth(slug: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/${slug}/health`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyResearchAgentChat(
  slug: string,
  body: {
    message: string;
    session_id?: string;
    history?: { role: "user" | "assistant"; content: string }[];
  },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/${slug}/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyHedgeFundFees(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/hedge-fund/fees`, {
    cache: "no-store",
    headers: buildHeaders(),
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

export async function proxyKickstartOrders(
  authToken: string,
  params?: { active_only?: boolean; limit?: number; refresh_metrics?: boolean }
): Promise<Response> {
  const search = new URLSearchParams();
  if (params?.active_only) search.set("active_only", "true");
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.refresh_metrics) search.set("refresh_metrics", "true");
  const qs = search.toString();
  return fetch(`${getAgentsBaseUrl()}/kickstart/orders${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyKickstartOrderExecutions(
  orderId: string,
  authToken: string,
  limit = 50
): Promise<Response> {
  const search = new URLSearchParams({ limit: String(limit) });
  return fetch(
    `${getAgentsBaseUrl()}/kickstart/orders/${encodeURIComponent(orderId)}/executions?${search}`,
    {
      cache: "no-store",
      headers: buildHeaders(authToken),
    }
  );
}

export async function proxyKickstartCancelOrder(
  orderId: string,
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/orders/${encodeURIComponent(orderId)}/cancel`, {
    method: "POST",
    headers: buildHeaders(authToken),
  });
}

export async function proxyKickstartUpdateOrder(
  orderId: string,
  body: { amount_sol?: number; limit_price_usd?: number; slippage_bps?: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/kickstart/orders/${encodeURIComponent(orderId)}`, {
    method: "PATCH",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyDcaHealth(pingLlm = false): Promise<Response> {
  return proxyAgentsHealth(pingLlm);
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

export async function proxyDcaWalletAgent(authToken?: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/wallet/agent`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyMultiWalletDemoAddress(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/multi-wallet-demo/address`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyMultiWalletDcaBalance(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/multi-wallet/dca/balance`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyMultiWalletDcaCreatePlan(
  body: { output_token: string; amount_per_buy: number; interval: string; max_executions: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/multi-wallet/dca/plan`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyMultiWalletDcaPlans(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/multi-wallet/dca/plans`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyMultiWalletDcaWithdraw(
  body: { token: string; amount: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/multi-wallet/dca/withdraw`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
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

export async function proxyDcaUpdatePlan(
  planId: string,
  body: {
    amount_per_buy?: number;
    interval?: string;
    max_executions?: number | null;
    total_budget?: number | null;
    slippage_bps?: number;
  },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/plans/${encodeURIComponent(planId)}`, {
    method: "PATCH",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
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

export async function proxyVolumeHealth(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/health`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyVolumeChat(
  body: { message: string; session_id?: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/chat`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyVolumeWalletAgent(): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/wallet/agent`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyVolumeWalletBalance(authToken: string): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/wallet/balance`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyVolumeDepositVerify(
  body: { signature: string },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/wallet/deposit/verify`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyVolumeWithdraw(
  body: { token: string; amount: number },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/wallet/withdraw`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyVolumeWalletLedger(
  authToken: string,
  limit = 50
): Promise<Response> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetch(`${getAgentsBaseUrl()}/volume/wallet/ledger?${params}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyVolumePoolCheck(baseToken: string, quoteToken = "SOL"): Promise<Response> {
  const params = new URLSearchParams({
    base_token: baseToken,
    quote_token: quoteToken,
  });
  return fetch(`${getAgentsBaseUrl()}/volume/pool/check?${params}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });
}

export async function proxyVolumePoolEnsure(
  body: { base_token: string; quote_token: string; create_if_missing: boolean },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/pool/ensure`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyVolumeCampaigns(
  authToken: string,
  params?: { active_only?: boolean; status?: string }
): Promise<Response> {
  const search = new URLSearchParams();
  if (params?.active_only) search.set("active_only", "true");
  if (params?.status) search.set("status", params.status);
  const qs = search.toString();
  return fetch(`${getAgentsBaseUrl()}/volume/campaigns${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
    headers: buildHeaders(authToken),
  });
}

export async function proxyVolumeCreateCampaign(
  body: {
    base_token: string;
    quote_token?: string;
    trade_amount: number;
    interval: string;
    max_executions: number;
    name?: string;
    total_budget?: number;
    slippage_bps?: number;
    seed_token_amount?: number;
  },
  authToken: string
): Promise<Response> {
  return fetch(`${getAgentsBaseUrl()}/volume/campaigns`, {
    method: "POST",
    headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
}

export async function proxyVolumeCampaignExecutions(
  campaignId: string,
  authToken: string
): Promise<Response> {
  return fetch(
    `${getAgentsBaseUrl()}/volume/campaigns/${encodeURIComponent(campaignId)}/executions`,
    {
      cache: "no-store",
      headers: buildHeaders(authToken),
    }
  );
}

export async function proxyVolumeCampaignStatus(
  campaignId: string,
  action: string,
  authToken: string
): Promise<Response> {
  return fetch(
    `${getAgentsBaseUrl()}/volume/campaigns/${encodeURIComponent(campaignId)}/status`,
    {
      method: "POST",
      headers: buildHeaders(authToken, { "Content-Type": "application/json" }),
      body: JSON.stringify({ action }),
    }
  );
}

export async function proxyVolumeCampaignProvision(
  campaignId: string,
  authToken: string
): Promise<Response> {
  return fetch(
    `${getAgentsBaseUrl()}/volume/campaigns/${encodeURIComponent(campaignId)}/provision`,
    {
      method: "POST",
      headers: buildHeaders(authToken),
    }
  );
}

export async function proxyVolumeAuthChallenge(userWallet: string): Promise<Response> {
  return proxyAgentsAuthChallenge(userWallet);
}

export async function proxyVolumeAuthVerify(body: {
  user_wallet: string;
  message: string;
  signature: string;
}): Promise<Response> {
  return proxyAgentsAuthVerify(body);
}

export async function proxyVolumeAuthMe(authToken: string): Promise<Response> {
  return proxyAgentsAuthMe(authToken);
}

export async function proxyVolumeResolveToken(query: string): Promise<Response> {
  return proxyDcaResolveToken(query);
}

export { getAuthToken, getAgentsBaseUrl, buildHeaders };
