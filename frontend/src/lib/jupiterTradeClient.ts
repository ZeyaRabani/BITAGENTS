import { mapApiActions, type AgentAction } from "@/lib/dcaAgentClient";

export type JupiterTradeHealth = {
  status: string;
  agent: string;
  model: string;
  auth_required: boolean;
  paper_min_hours?: number;
  venue?: string;
  perps_enabled?: boolean;
  cluster?: string;
  trading_wallet?: string | null;
  trading_wallet_configured?: boolean;
  wallet_provider?: string | null;
  signing?: string;
  monitor_interval_seconds?: number;
  strategy_templates?: number;
  platform_fee_pct?: number;
};

export type JupiterTradeTemplate = {
  id: string;
  name: string;
  family: string;
  summary: string;
  default_tp_pct?: number;
  default_sl_pct?: number;
  timeframe?: string;
  aliases?: string[];
};

export type JupiterTradeTemplatesResponse = {
  count: number;
  total_catalog: number;
  families: string[];
  templates: JupiterTradeTemplate[];
};

export type JupiterTradeChatResponse = {
  reply: string;
  session_id: string;
  actions: { tool: string; args: Record<string, unknown>; result: string }[];
};

export type JupiterTradeGate = {
  paper_min_hours: number;
  hours_elapsed: number;
  hours_remaining: number;
  ready_for_live_confirm: boolean;
  status?: string;
};

export type JupiterTradeStrategy = {
  id: string;
  name: string;
  status: string;
  symbols?: string[];
  understanding?: string;
  capital_sol?: number;
  cash_sol?: number;
  paper_started_at?: string;
  paper_ready_at?: string;
  live_started_at?: string;
  rules?: {
    take_profit_pct?: number;
    stop_loss_pct?: number;
    notes?: string;
    template_id?: string;
    template_name?: string;
    template_family?: string;
  };
  gate?: JupiterTradeGate;
  positions?: {
    symbol: string;
    units: number;
    avg_entry_usd?: number;
    mark_price_usd?: number;
    unrealized_pnl_pct?: number;
  }[];
  recent_trades?: {
    id?: string;
    symbol?: string;
    side?: string;
    price_usd?: number;
    notional_usd?: number;
    reason?: string;
    mode?: string;
    created_at?: string;
    signature?: string;
  }[];
};

export type JupiterTradeDashboard = {
  strategies: JupiterTradeStrategy[];
  paper_min_hours: number;
  venue: string;
  perps_enabled: boolean;
};

async function readJson(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof data.detail === "string" ? data.detail : data.error ?? "Request failed";
    throw new Error(detail);
  }
  return data;
}

export async function fetchJupiterTradeHealth(): Promise<JupiterTradeHealth | null> {
  try {
    const res = await fetch("/api/agents/jupiter-trade/health", { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as JupiterTradeHealth;
  } catch {
    return null;
  }
}

export async function sendJupiterTradeMessage(
  message: string,
  authToken: string,
  sessionId?: string,
  history?: { role: "user" | "assistant"; content: string }[]
): Promise<JupiterTradeChatResponse> {
  const res = await fetch("/api/agents/jupiter-trade/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify({ message, session_id: sessionId, history }),
  });
  return (await readJson(res)) as JupiterTradeChatResponse;
}

export function mapJupiterTradeActions(
  actions: JupiterTradeChatResponse["actions"]
): AgentAction[] {
  return mapApiActions(actions);
}

export async function fetchJupiterTradeDashboard(
  authToken: string
): Promise<JupiterTradeDashboard> {
  const res = await fetch("/api/agents/jupiter-trade/dashboard", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return (await readJson(res)) as JupiterTradeDashboard;
}

export async function fetchJupiterTradeWallet(authToken: string) {
  const res = await fetch("/api/agents/jupiter-trade/wallet/agent", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return readJson(res);
}

export async function fetchJupiterTradeTemplates(params?: {
  family?: string;
  query?: string;
  limit?: number;
}): Promise<JupiterTradeTemplatesResponse> {
  const search = new URLSearchParams();
  if (params?.family) search.set("family", params.family);
  if (params?.query) search.set("query", params.query);
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  const res = await fetch(`/api/agents/jupiter-trade/templates${qs ? `?${qs}` : ""}`, {
    cache: "no-store",
  });
  return (await readJson(res)) as JupiterTradeTemplatesResponse;
}

export async function createJupiterTradeStrategy(
  authToken: string,
  body: {
    name?: string;
    symbols: string;
    capital_sol?: number;
    take_profit_pct?: number;
    stop_loss_pct?: number;
    notes?: string;
    template_id?: string;
  }
) {
  const res = await fetch("/api/agents/jupiter-trade/strategies", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  return readJson(res);
}

export async function confirmJupiterTradeUnderstanding(
  authToken: string,
  strategyId: string
) {
  const res = await fetch(
    `/api/agents/jupiter-trade/strategies/${encodeURIComponent(strategyId)}/confirm-understanding`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
    }
  );
  return readJson(res);
}

export async function confirmJupiterTradeLive(authToken: string, strategyId: string) {
  const res = await fetch(
    `/api/agents/jupiter-trade/strategies/${encodeURIComponent(strategyId)}/confirm-live`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
    }
  );
  return readJson(res);
}

export async function closeJupiterTradeStrategy(authToken: string, strategyId: string) {
  const res = await fetch(
    `/api/agents/jupiter-trade/strategies/${encodeURIComponent(strategyId)}/close`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${authToken}` },
    }
  );
  return readJson(res);
}

export async function runJupiterTradeMonitor(authToken: string) {
  const res = await fetch("/api/agents/jupiter-trade/monitor", {
    method: "POST",
    headers: { Authorization: `Bearer ${authToken}` },
  });
  return readJson(res);
}
